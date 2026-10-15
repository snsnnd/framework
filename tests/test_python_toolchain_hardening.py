#!/usr/bin/env python3
"""Focused tests for Python toolchain safety without hardware dependencies."""

from __future__ import annotations

import asyncio
import argparse
import io
import stat
import tarfile
import tempfile
import unittest
import zipfile
import sys
import json
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.api.flash import build_flash_command, run_flash
from tools.api.build import build_project, project_chip
from tools.api.project import set_project_fields
from tools.board.stm32_bsp import BSPGenerationError, generate_stm32_bsp
from tools.compiler.cmake_generator import CMakeGenerator
from tools.codegen.validate import validate_graph
from tools.compiler.compiler import CompilerInfo, CompilerManager, ProjectCompiler
from tools.firmware.manager import FirmwareManager, safe_extract_tar, safe_extract_zip
from tools.firmware.stm32 import STM32SDKError, prepare_stm32_build
from tools.groundstation.daemon_frames import LiteTuneSerialProtocol, handle_log_report
from tools.groundstation.daemon_state import DaemonState
from tools.groundstation.protocol import RawFrame, TYPE_IDS
from tools.groundstation import cli as groundstation_cli
from tools import efw
from tools.target import TargetResolutionError, resolve_project_target, resolve_target
from tools.studio.model import load_board_profiles


def make_state(root: Path, **kwargs: object) -> DaemonState:
    return DaemonState(
        port="fake",
        baud=115200,
        socket_path=str(root / "daemon.sock"),
        log_path=str(root / "events.jsonl"),
        daemon_json_path=str(root / "daemon.json"),
        runtime_dir=str(root),
        **kwargs,
    )


class GroundStationBoundsTest(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_frame_is_dropped_until_delimiter_then_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(Path(tmp), host_max_decoded_frame=16, rx_queue_size=2)
            protocol = LiteTuneSerialProtocol(state)

            protocol.data_received(b"x" * 40)
            self.assertTrue(protocol.dropping_oversized_frame)
            self.assertLessEqual(len(protocol.buf), protocol.max_wire_frame_size)
            protocol.data_received(b"ignored\x00valid\x00")

            self.assertFalse(protocol.dropping_oversized_frame)
            self.assertEqual(await state.rx_queue.get(), b"valid")
            self.assertEqual(state.stats["rx_overflows"], 1)

    async def test_rx_queue_drops_new_frames_when_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(Path(tmp), rx_queue_size=1)
            protocol = LiteTuneSerialProtocol(state)
            protocol.data_received(b"one\x00two\x00")
            self.assertEqual(await state.rx_queue.get(), b"one")
            self.assertEqual(state.stats["rx_queue_dropped"], 1)
            self.assertEqual(state.tx_queue.maxsize, 64)

    async def test_telemetry_drops_instead_of_blocking_on_full_log_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(Path(tmp), log_queue_size=1)
            state.log_queue.put_nowait({"occupied": True})
            frame = RawFrame(TYPE_IDS["LOG_REPORT"], 1, b"\x01\x01\x00payload")

            await asyncio.wait_for(handle_log_report(state, frame), timeout=0.1)

            self.assertEqual(state.stats["telemetry_dropped"], 1)
            self.assertEqual(state.stats["log_queue_dropped"], 1)
            self.assertEqual(state.log_queue.qsize(), 1)


class FirmwareSafetyTest(unittest.TestCase):
    def test_zip_traversal_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, configure in (
                ("traversal.zip", lambda info: None),
                ("symlink.zip", lambda info: setattr(info, "external_attr", (stat.S_IFLNK | 0o777) << 16)),
            ):
                archive_path = root / name
                with zipfile.ZipFile(archive_path, "w") as archive:
                    info = zipfile.ZipInfo("../escape" if name == "traversal.zip" else "link")
                    configure(info)
                    archive.writestr(info, "target")
                with zipfile.ZipFile(archive_path) as archive:
                    with self.assertRaises(ValueError):
                        safe_extract_zip(archive, root / "out")
            self.assertFalse((root / "escape").exists())

    def test_tar_traversal_and_links_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            traversal = root / "traversal.tar"
            with tarfile.open(traversal, "w") as archive:
                info = tarfile.TarInfo("../escape")
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))
            with tarfile.open(traversal) as archive:
                with self.assertRaises(ValueError):
                    safe_extract_tar(archive, root / "out")

            linked = root / "linked.tar"
            with tarfile.open(linked, "w") as archive:
                info = tarfile.TarInfo("link")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../escape"
                archive.addfile(info)
            with tarfile.open(linked) as archive:
                with self.assertRaises(ValueError):
                    safe_extract_tar(archive, root / "out")

    def test_remove_rejects_root_managed_directory_and_external_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            managed = root / "firmware"
            manager = FirmwareManager(managed)
            external = root / "external"
            external.mkdir()
            for name, path in (("root", Path(path_anchor())), ("managed", managed), ("external", external)):
                manager.config[name] = {"path": str(path)}
                self.assertFalse(manager.remove(name))
                self.assertTrue(path.exists())
            manager.config["empty"] = {"path": ""}
            self.assertFalse(manager.remove("empty"))


def path_anchor() -> str:
    return Path.cwd().anchor


def make_stm32_sdk(root: Path, family: str, startup_name: str) -> FirmwareManager:
    sdk_name = family.lower()
    sdk_root = root / sdk_name
    device_root = sdk_root / "Drivers" / "CMSIS" / "Device" / "ST" / f"{family}xx"
    startup_dir = device_root / "Source" / "Templates" / "gcc"
    hal_root = sdk_root / "Drivers" / f"{family}xx_HAL_Driver"
    for directory in (
        sdk_root / "Drivers" / "CMSIS" / "Include",
        device_root / "Include",
        startup_dir,
        hal_root / "Inc" / "Legacy",
        hal_root / "Src",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (startup_dir / startup_name).write_text(".section .isr_vector\n")
    (device_root / "Source" / "Templates" / f"system_{family.lower()}xx.c").write_text("void SystemInit(void) {}\n")
    (hal_root / "Inc" / f"{family.lower()}xx_hal_conf_template.h").write_text("#define HAL_MODULE_ENABLED\n")
    (hal_root / "Src" / f"{family.lower()}xx_hal.c").write_text("void HAL_Init(void) {}\n")
    manager = FirmwareManager(root / "managed")
    manager.config[sdk_name] = {"path": str(sdk_root)}
    return manager


def make_stm32_bsp(project: Path, family: str) -> None:
    include_dir = project / "include"
    include_dir.mkdir(parents=True, exist_ok=True)
    (include_dir / f"{family.lower()}xx_hal_conf.h").write_text("#define HAL_MODULE_ENABLED\n")
    (project / "board_adapter.c").write_text(
        '#include "efw/efw.h"\nefw_status_t app_board_init(void) { return EFW_OK; }\n'
    )
    (project / "main.c").write_text(
        "int app_board_init(void); int main(void) { if (app_board_init() != 0) return 1; return 0; }\n"
    )


class CompilerGenerationTest(unittest.TestCase):
    def test_public_toolchain_surface_only_exposes_verified_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compiler_manager = CompilerManager(root / "compilers")
            self.assertEqual([item["name"] for item in compiler_manager.list_compilers()], ["arm-gcc"])
            self.assertIsNone(compiler_manager.get_compiler_for_chip("ESP32-S3"))
            self.assertFalse(compiler_manager.set_compiler_path("iar", root))

            firmware_manager = FirmwareManager(root / "firmware")
            self.assertEqual({item["name"] for item in firmware_manager.list_firmwares()}, {"stm32f1", "stm32f4", "stm32g4"})
            self.assertIsNone(firmware_manager.get_firmware_for_chip("ESP32-S3"))
            self.assertFalse(firmware_manager.download("esp-idf", local_path=root))

    def test_generates_bsp_for_every_stm32_target(self) -> None:
        targets = {
            "STM32F103C8T6": "Blue_Pill",
            "STM32F103RBT6": "Nucleo_F103RB",
            "STM32F407VGT6": "Discovery_F407",
            "STM32F411RET6": "Nucleo_F411RE",
            "STM32F446RET6": "Nucleo_F446RE",
            "STM32G431CBT6": "Nucleo_G431CB",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for chip, profile in targets.items():
                with self.subTest(chip=chip):
                    project = root / chip
                    generated = generate_stm32_bsp(project, resolve_target(chip=chip), profile)
                    source = generated.source.read_text()
                    config = generated.hal_config.read_text()
                    self.assertIn("efw_status_t app_board_init(void)", source)
                    self.assertIn("HAL_RCC_OscConfig", source)
                    self.assertIn("HAL_RCC_ClockConfig", source)
                    self.assertIn("HAL_GPIO_Init", source) if chip != "STM32G431CBT6" else self.assertNotIn("HAL_GPIO_Init", source)
                    self.assertIn("HAL_RCC_MODULE_ENABLED", config)
                    self.assertIn("HSI48_VALUE", config)

            blue_pill = (root / "STM32F103C8T6" / ".efw_target" / "board_adapter.c").read_text()
            self.assertIn("HAL_GPIO_WritePin(GPIOC, GPIO_PIN_13, GPIO_PIN_SET)", blue_pill)
            self.assertIn("GPIO_MODE_OUTPUT_PP", blue_pill)
            f446 = (root / "STM32F446RET6" / ".efw_target" / "board_adapter.c").read_text()
            self.assertIn("HAL_PWREx_EnableOverDrive", f446)
            g431 = (root / "STM32G431CBT6" / ".efw_target" / "board_adapter.c").read_text()
            self.assertIn("RCC_PLLR_DIV2", g431)
            self.assertNotIn("USART2", g431)
            self.assertNotIn("I2C1", g431)
            self.assertNotIn("SPI1", g431)

    def test_non_concrete_and_mismatched_bsp_profiles_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(BSPGenerationError):
                generate_stm32_bsp(root, resolve_target(chip="STM32F103C8T6"), "stm32f103c8")
            with self.assertRaises(BSPGenerationError):
                generate_stm32_bsp(root, resolve_target(chip="STM32F103C8T6"), "stm32-basic")
            with self.assertRaises((BSPGenerationError, TargetResolutionError)):
                generate_stm32_bsp(root, resolve_target(chip="STM32F407VGT6"), "Blue_Pill")

    def test_cmake_uses_strict_target_and_rejects_unsupported_chip(self) -> None:
        generator = CMakeGenerator(Path("/tmp/project"), Path("/tmp/firmware"))
        cmake = generator.generate("STM32F407VGT6")
        toolchain = generator.generate_toolchain_file()

        self.assertIn(f'set(EFW_ROOT "{Path(__file__).resolve().parents[1]}")', cmake)
        self.assertIn("${EFW_ROOT}/src/app/*.c", cmake)
        self.assertIn("-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16", cmake)
        self.assertIn('set(CMAKE_C_COMPILER "${TOOLCHAIN_PREFIX}gcc")', toolchain)
        self.assertNotIn("${{", toolchain)
        self.assertIn("CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY", toolchain)
        with self.assertRaises(TargetResolutionError):
            generator.generate("STM32H743ZI")

    def test_project_compiler_keeps_same_basename_objects_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            first = project / "src" / "a" / "same.c"
            second = project / "src" / "b" / "same.c"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("int a;\n")
            second.write_text("int b;")
            make_stm32_bsp(project, "STM32F4")
            firmware_manager = make_stm32_sdk(project / "firmware", "STM32F4", "startup_stm32f407xx.s")
            compiler = CompilerInfo("arm-gcc", "test", [], "arm-none-eabi-gcc", [])
            compiler.found_path = project / "toolchain"
            project_compiler = ProjectCompiler(project, firmware_manager=firmware_manager)
            commands: list[list[str]] = []

            def fake_run(command: list[str], **kwargs: object) -> mock.Mock:
                commands.append(command)
                executable = Path(command[0]).name
                if "-o" in command:
                    output = Path(command[command.index("-o") + 1])
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"output")
                elif executable.endswith("objcopy"):
                    Path(command[-1]).write_bytes(b"output")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(project_compiler.compiler_manager, "get_compiler", return_value=compiler), mock.patch(
                "tools.compiler.compiler.subprocess.run", side_effect=fake_run
            ):
                self.assertTrue(project_compiler.compile("STM32F407VGT6", [first, second]))

            outputs = [Path(command[command.index("-o") + 1]) for command in commands[:2]]
            self.assertEqual(len(set(outputs)), 2)
            self.assertEqual(outputs[0], project / "build" / "obj" / "src" / "a" / "same.o")
            self.assertEqual(outputs[1], project / "build" / "obj" / "src" / "b" / "same.o")
            compile_commands = [command for command in commands if "-c" in command]
            self.assertTrue(any(any(Path(arg).name == "system_stm32f4xx.c" for arg in command) for command in compile_commands))
            self.assertTrue(any(str(project / ".efw_target" / "startup.s") in command for command in compile_commands))
            self.assertIn("-D", compile_commands[0])
            self.assertTrue((project / ".efw_target" / "linker.ld").is_file())

    def test_project_compiler_adds_generated_bsp_to_explicit_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            main = project / "main.c"
            main.write_text(
                '#include "efw/efw.h"\nextern efw_status_t app_board_init(void);\n'
                'int main(void) { if (app_board_init() != EFW_OK) return 1; for (;;) {} }\n'
            )
            firmware_manager = make_stm32_sdk(project / "firmware", "STM32F1", "startup_stm32f103xb.s")
            compiler = CompilerInfo("arm-gcc", "test", [], "arm-none-eabi-gcc", [])
            compiler.found_path = project / "toolchain"
            project_compiler = ProjectCompiler(
                project,
                firmware_manager=firmware_manager,
                board_profile="Blue_Pill",
            )
            commands: list[list[str]] = []

            def fake_run(command: list[str], **kwargs: object) -> mock.Mock:
                commands.append(command)
                executable = Path(command[0]).name
                if executable.endswith("objcopy"):
                    Path(command[-1]).write_bytes(b"output")
                elif "-o" in command:
                    output = Path(command[command.index("-o") + 1])
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(b"output")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(project_compiler.compiler_manager, "get_compiler", return_value=compiler), mock.patch(
                "tools.compiler.compiler.subprocess.run", side_effect=fake_run
            ):
                self.assertTrue(project_compiler.compile("STM32F103C8T6", [main]))

            compile_commands = [command for command in commands if "-c" in command]
            self.assertTrue(any(str(project / ".efw_target" / "board_adapter.c") in command for command in compile_commands))

    def test_project_compiler_fails_before_toolchain_without_target_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_compiler = ProjectCompiler(Path(tmp))
            with mock.patch.object(project_compiler.compiler_manager, "get_compiler") as get_compiler:
                self.assertFalse(project_compiler.compile("STM32F407VGT6"))
                get_compiler.assert_not_called()

    def test_stm32_sdk_resolver_requires_bsp_and_generates_exact_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = make_stm32_sdk(root / "firmware", "STM32G4", "startup_stm32g431xx.s")
            target = resolve_target(chip="STM32G431CBT6")
            (root / "include").mkdir()
            (root / "include" / "stm32g4xx_hal_conf.h").write_text("#define HAL_MODULE_ENABLED\n")
            with self.assertRaisesRegex(STM32SDKError, "app_board_init"):
                prepare_stm32_build(root, target, manager)

            make_stm32_bsp(root, "STM32G4")
            resources = prepare_stm32_build(root, target, manager)
            self.assertEqual(resources.startup, root / ".efw_target" / "startup.s")
            self.assertIn(".section .isr_vector", resources.startup.read_text())
            linker = resources.linker.read_text()
            self.assertIn("LENGTH = 128K", linker)
            self.assertIn("LENGTH = 32K", linker)
            self.assertTrue(any(path.name == "system_stm32g4xx.c" for path in resources.sources))
            self.assertTrue(any(path.name == "stm32g4xx_hal.c" for path in resources.sources))

    def test_stm32_sdk_resolver_accepts_single_nested_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = make_stm32_sdk(root / "firmware", "STM32F1", "startup_stm32f103xb.s")
            sdk_path = Path(manager.config["stm32f1"]["path"])
            wrapper = root / "wrapper"
            wrapper.mkdir()
            nested_sdk = sdk_path.rename(wrapper / "STM32CubeF1-master")
            manager.config["stm32f1"]["path"] = str(wrapper)
            make_stm32_bsp(root, "STM32F1")

            resources = prepare_stm32_build(root, resolve_target(chip="STM32F103C8T6"), manager)

            self.assertEqual(resources.sdk_root, nested_sdk)

    def test_user_bsp_does_not_reuse_generated_hal_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = make_stm32_sdk(root / "firmware", "STM32F4", "startup_stm32f407xx.s")
            generated = generate_stm32_bsp(root, resolve_target(chip="STM32F407VGT6"), "Discovery_F407")
            (root / "board_adapter.c").write_text(
                '#include "efw/efw.h"\nefw_status_t app_board_init(void) { return EFW_OK; }\n'
            )
            (root / "main.c").write_text(
                "int app_board_init(void); int main(void) { if (app_board_init() != 0) return 1; return 0; }\n"
            )

            with self.assertRaisesRegex(STM32SDKError, "HAL 配置"):
                prepare_stm32_build(root, resolve_target(chip="STM32F407VGT6"), manager)
            self.assertTrue(generated.hal_config.is_file())

    def test_all_stm32_targets_declare_expected_cube_startup(self) -> None:
        expected = {
            "STM32F103C8T6": "startup_stm32f103xb.s",
            "STM32F103RBT6": "startup_stm32f103xb.s",
            "STM32F407VGT6": "startup_stm32f407xx.s",
            "STM32F411RET6": "startup_stm32f411xe.s",
            "STM32F446RET6": "startup_stm32f446xx.s",
            "STM32G431CBT6": "startup_stm32g431xx.s",
        }
        self.assertEqual({chip: resolve_target(chip=chip).startup_source for chip in expected}, expected)

    def test_project_build_keeps_project_and_build_directories_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            graph = root / "graph.json"
            output = root / "generated"
            build = root / "out"
            descriptor = root / "demo.efw_project.json"
            graph.write_text('{"project":{"name":"demo","chip":"STM32F407VGT6"},"board":{"profile":"Discovery_F407"}}')
            descriptor.write_text(
                '{"name":"demo","chip":"STM32F407VGT6","board_profile":"Discovery_F407",'
                f'"graph_path":"{graph}","output_dir":"{output}"}}'
            )
            with mock.patch("tools.compiler.compiler.ProjectCompiler") as compiler_type:
                compiler_type.return_value.compile.return_value = True
                self.assertEqual(build_project(descriptor, build_dir=str(build)), 0)
            compiler_type.assert_called_once_with(output, build, board_profile="Discovery_F407")
            compiler_type.return_value.compile.assert_called_once_with("STM32F407VGT6")

    def test_installed_cube_f4_layout_resolves_when_available(self) -> None:
        sdk_root = Path.home() / ".efw" / "firmware" / "stm32f4"
        if not sdk_root.is_dir():
            self.skipTest("managed STM32CubeF4 is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            make_stm32_bsp(project, "STM32F4")
            manager = FirmwareManager(project / "managed")
            manager.config["stm32f4"] = {"path": str(sdk_root)}
            for chip in ("STM32F407VGT6", "STM32F411RET6", "STM32F446RET6"):
                with self.subTest(chip=chip):
                    resources = prepare_stm32_build(project, resolve_target(chip=chip), manager)
                    self.assertTrue(resources.startup.is_file())
                    self.assertTrue(any(path.name == "system_stm32f4xx.c" for path in resources.sources))


class FlashTest(unittest.TestCase):
    def test_all_tools_build_actual_program_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Path(tmp) / "app.bin"
            firmware.write_bytes(b"firmware")
            stlink = build_flash_command(firmware, chip="STM32F411RET6", tool="stlink", port="123")
            jlink = build_flash_command(firmware, chip="STM32F411RET6", tool="jlink", port="456")
            openocd = build_flash_command(firmware, chip="STM32F411RET6", tool="openocd", port="789", erase=True)

            self.assertIn(str(firmware.resolve()), stlink)
            self.assertIn("-SelectEmuBySN", jlink)
            self.assertIn("456", jlink)
            self.assertIn("STM32F411RE", jlink)
            self.assertIn("target/stm32f4x.cfg", openocd)
            self.assertIn(f"program {{{firmware.resolve()}}} verify reset exit 0x08000000", openocd)
            self.assertIn("adapter serial 789", openocd)

    def test_dry_run_does_not_execute_and_jlink_uses_program_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Path(tmp) / "app.bin"
            firmware.write_bytes(b"firmware")
            with mock.patch("tools.api.flash.subprocess.run") as run:
                run_flash(firmware, chip="STM32G431CBT6", tool="openocd", dry_run=True)
                run.assert_not_called()

                run_flash(firmware, chip="STM32G431CBT6", tool="jlink", erase=True)
                script = run.call_args.kwargs["input"]
                self.assertIn("erase\n", script)
                self.assertIn(f'loadbin "{firmware.resolve()}", 0x08000000', script)

    def test_cli_executes_by_default_and_dry_run_is_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Path(tmp) / "app.bin"
            firmware.write_bytes(b"firmware")
            with mock.patch("tools.api.flash.run_flash", return_value=["st-flash"]) as flash:
                self.assertEqual(efw.cmd_flash(["--bin", str(firmware), "--chip", "STM32F407VGT6"]), 0)
                self.assertFalse(flash.call_args.kwargs["dry_run"])
                self.assertEqual(efw.cmd_flash(["--bin", str(firmware), "--chip", "STM32F407VGT6", "--dry-run"]), 0)
                self.assertTrue(flash.call_args.kwargs["dry_run"])

    def test_probe_serial_rejects_control_and_interpreter_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Path(tmp) / "app.bin"
            firmware.write_bytes(b"firmware")
            for port in ("123\nshutdown", "123;shutdown", "123${evil}", '123"evil'):
                for tool in ("stlink", "jlink", "openocd"):
                    with self.subTest(port=port, tool=tool), self.assertRaises(ValueError):
                        build_flash_command(firmware, chip="STM32F407VGT6", tool=tool, port=port)

    def test_script_paths_reject_control_and_interpreter_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe_path = root / "firmware image.bin"
            safe_path.write_bytes(b"firmware")
            build_flash_command(safe_path, chip="STM32F407VGT6", tool="openocd")
            build_flash_command(safe_path, chip="STM32F407VGT6", tool="jlink")

            for name in ("evil\nshutdown.bin", "evil\u2028shutdown.bin", 'evil"exit.bin', "evil};shutdown.bin", "evil$cmd.bin"):
                firmware = root / name
                firmware.write_bytes(b"firmware")
                for tool in ("stlink", "jlink", "openocd"):
                    with self.subTest(name=name, tool=tool), self.assertRaises(ValueError):
                        build_flash_command(firmware, chip="STM32F407VGT6", tool=tool)


class TargetResolutionTest(unittest.TestCase):
    def test_board_profile_resolves_canonical_target(self) -> None:
        target = resolve_target(board_profile="Nucleo_G431CB")
        self.assertEqual(target.chip, "STM32G431CBT6")
        self.assertEqual(target.toolchain, "arm-gcc")
        self.assertEqual(target.sdk, "stm32g4")
        self.assertIn("STM32G431xx", target.defines)
        self.assertEqual(target.flash["openocd_target"], "target/stm32g4x.cfg")

    def test_project_and_graph_target_conflicts_fail_closed(self) -> None:
        project = {"chip": "STM32F407VGT6", "board_profile": "Nucleo_F411RE"}
        with self.assertRaisesRegex(TargetResolutionError, "目标冲突"):
            resolve_project_target(project)

        graph = {"project": {"chip": "STM32F411RET6"}, "board": {"profile": "stm32-basic"}}
        with self.assertRaisesRegex(TargetResolutionError, "目标芯片不一致"):
            resolve_project_target({"chip": "STM32F407VGT6"}, graph)

        with self.assertRaisesRegex(TargetResolutionError, "目标芯片不一致"):
            resolve_project_target({"chip": "STM32F407VGT6"}, chip="STM32F411RET6")

    def test_missing_and_unknown_targets_do_not_fallback_to_f407(self) -> None:
        with self.assertRaises(TargetResolutionError):
            project_chip({"board_profile": "stm32-basic"})
        with self.assertRaises(TargetResolutionError):
            resolve_target(chip="ESP32-S3")

    def test_flash_requires_target_and_uses_target_specific_device(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            firmware = Path(tmp) / "app.bin"
            firmware.write_bytes(b"firmware")
            with self.assertRaises(TargetResolutionError):
                build_flash_command(firmware)
            command = build_flash_command(firmware, chip="STM32F103C8T6", tool="jlink")
            self.assertIn("STM32F103C8", command)

    def test_board_profile_routes_exist_in_target_mcu_data(self) -> None:
        board_targets = {
            "Blue_Pill": "STM32F103C8T6",
            "Nucleo_F103RB": "STM32F103RBT6",
            "Discovery_F407": "STM32F407VGT6",
            "Nucleo_F411RE": "STM32F411RET6",
            "Nucleo_F446RE": "STM32F446RET6",
            "Nucleo_G431CB": "STM32G431CBT6",
        }
        root = Path(__file__).resolve().parents[1]
        mcu_index = json.loads((root / "data" / "mcu" / "index.json").read_text())
        for profile_name, chip in board_targets.items():
            profile = json.loads((root / "data" / "board_profiles" / f"{profile_name}.json").read_text())
            mcu = json.loads((root / "data" / "mcu" / mcu_index[chip]["path"]).read_text())
            pins = {str(pin).split("-", 1)[0] for pin in mcu["gpio_pins"]}
            self.assertTrue(profile.get("sources"), profile_name)
            for route_name, route in profile["pins"].items():
                for field in ("pin", "tx", "rx", "scl", "sda", "sck", "miso", "mosi", "cs"):
                    if route.get(field):
                        self.assertIn(route[field], pins, f"{profile_name}.{route_name}.{field}")

    def test_board_profile_loader_preserves_sourced_routes(self) -> None:
        profiles = load_board_profiles()
        nucleo = profiles["Nucleo_F446RE"]
        self.assertEqual(nucleo["pins"]["uart_debug"]["tx"], "PA2")
        self.assertEqual(nucleo["clock"]["source"], "HSE")
        self.assertTrue(nucleo["sources"])
        self.assertEqual(profiles["Nucleo_G431CB"]["board_type"], "custom")


class GraphHardwareValidationTest(unittest.TestCase):
    @staticmethod
    def minimal_graph(nodes: list[dict], edges: list[dict] | None = None, *, pin_plan: list[dict] | None = None) -> dict:
        return {
            "project": {"name": "validation", "tick_ms": 1, "chip": "STM32F103C8T6"},
            "board": {"profile": "Blue_Pill", "pin_plan": pin_plan or []},
            "nodes": nodes,
            "edges": edges or [],
            "flows": [],
            "tasks": [],
            "custom_files": [],
            "board_adapters": [],
        }

    def test_rejects_invalid_ports_cycles_duplicate_topics_and_c_idents(self) -> None:
        nodes = [
            {"id": "src", "type": "sensor.custom", "read": "read_src", "output_type": "float"},
            {"id": "proc", "type": "processor.custom", "process": "run_proc", "input_type": "float", "output_type": "float"},
        ]
        graph = self.minimal_graph(nodes, [{"id": "bad", "from": "src", "to": "proc", "from_port": "bogus", "to_port": "sensor", "kind": "data_flow"}])
        with self.assertRaisesRegex(ValueError, "节点/端口组合不受支持"):
            validate_graph(graph)

        cycle_nodes = [
            {"id": "proc", "type": "processor.custom", "process": "run_proc", "input_type": "float", "output_type": "float"},
            {"id": "algo", "type": "algorithm.custom", "run": "run_algo", "input_type": "float", "output_type": "float"},
        ]
        graph = self.minimal_graph(cycle_nodes, [
            {"id": "e1", "from": "proc", "to": "algo", "from_port": "algorithm", "to_port": "processor", "kind": "data_flow"},
            {"id": "e2", "from": "algo", "to": "proc", "from_port": "algorithm", "to_port": "algorithm", "kind": "control_flow"},
        ])
        with self.assertRaisesRegex(ValueError, "cycle detected"):
            validate_graph(graph)

        graph = self.minimal_graph([
            {"id": "topic_a", "type": "event.topic", "topic_id": 7, "payload_type": "float"},
            {"id": "topic_b", "type": "event.topic", "topic_id": 7, "payload_type": "float"},
        ])
        with self.assertRaisesRegex(ValueError, "topic_id 7 重复"):
            validate_graph(graph)

        graph = self.minimal_graph([
            {"id": "motor-a", "type": "project.module"},
            {"id": "motor_a", "type": "project.module"},
        ])
        with self.assertRaisesRegex(ValueError, "相同 C 标识符"):
            validate_graph(graph)

    def test_rejects_unsupported_publisher_source_and_missing_board_callbacks(self) -> None:
        graph = self.minimal_graph([
            {"id": "topic", "type": "event.topic", "topic_id": 1, "payload_type": "float"},
            {"id": "algorithm", "type": "algorithm.custom", "run": "run_algorithm", "output_type": "float"},
            {"id": "publisher", "type": "event.publisher", "topic": "topic", "source": "algorithm"},
        ])
        with self.assertRaisesRegex(ValueError, "不支持自动发布"):
            validate_graph(graph)

        graph = self.minimal_graph([
            {"id": "line", "type": "hal.gpio_line_input", "channels": 1, "pins": [{"port": "A", "pin": 0}]},
        ])
        with self.assertRaisesRegex(ValueError, "app_board_read_line_input"):
            validate_graph(graph)

        graph = self.minimal_graph([
            {"id": "motor", "type": "actuator.motor", "pwm": {"timer": 1, "channel": 1}, "dir_pin": {"port": "B", "pin": 0}},
        ])
        with self.assertRaisesRegex(ValueError, "app_board_write_motor"):
            validate_graph(graph)

    def test_pin_plan_validates_package_pwm_and_physical_conflicts(self) -> None:
        nodes = [{"id": "a", "type": "project.module"}, {"id": "b", "type": "project.module"}]
        graph = self.minimal_graph(nodes, pin_plan=[{"node": "a", "usage": "GPIO", "port": "PA", "pin": "0"}])
        ctx = validate_graph(graph)
        self.assertEqual(ctx["board"]["pin_plan"][0]["port"], "A")
        self.assertEqual(ctx["board"]["pin_plan"][0]["pin"], 0)

        graph = self.minimal_graph(nodes, pin_plan=[{"node": "a", "usage": "GPIO", "port": "E", "pin": 0}])
        with self.assertRaisesRegex(ValueError, "不属于目标"):
            validate_graph(graph)

        graph = self.minimal_graph(nodes, pin_plan=[
            {"node": "a", "usage": "GPIO", "port": "A", "pin": 8},
            {"node": "b", "usage": "PWM", "timer": 1, "channel": 1},
        ])
        with self.assertRaisesRegex(ValueError, "物理引脚冲突"):
            validate_graph(graph)


class ProjectTargetSyncTest(unittest.TestCase):
    @staticmethod
    def make_project(root: Path, *, chip: str = "STM32F407VGT6", board: str = "Discovery_F407") -> tuple[Path, Path]:
        graph_path = root / "graph.json"
        descriptor = root / "demo.efw_project.json"
        graph_path.write_text(json.dumps({
            "project": {"name": "demo", "tick_ms": 1, "chip": chip},
            "board": {"profile": board, "pin_plan": []},
            "nodes": [{"id": "app", "type": "project.module"}],
            "edges": [], "flows": [], "tasks": [], "custom_files": [],
        }))
        descriptor.write_text(json.dumps({
            "kind": "efw.project", "schema_version": 1, "name": "demo",
            "chip": chip, "board_profile": board, "graph_path": str(graph_path),
            "output_dir": str(root / "generated"),
        }))
        return descriptor, graph_path

    def test_target_edits_synchronize_descriptor_and_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            descriptor, graph_path = self.make_project(Path(tmp))
            set_project_fields(descriptor, board="Nucleo_F411RE")
            project = json.loads(descriptor.read_text())
            graph = json.loads(graph_path.read_text())
            self.assertEqual((project["chip"], graph["project"]["chip"]), ("STM32F411RET6", "STM32F411RET6"))
            self.assertEqual((project["board_profile"], graph["board"]["profile"]), ("Nucleo_F411RE", "Nucleo_F411RE"))

    def test_conflicting_target_edit_rolls_back_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            descriptor, graph_path = self.make_project(Path(tmp))
            before_descriptor = descriptor.read_bytes()
            before_graph = graph_path.read_bytes()
            with self.assertRaises(TargetResolutionError):
                set_project_fields(descriptor, chip="STM32F103C8T6", board="Discovery_F407")
            self.assertEqual(descriptor.read_bytes(), before_descriptor)
            self.assertEqual(graph_path.read_bytes(), before_graph)


class GroundStationCliSafetyTest(unittest.TestCase):
    def test_force_stop_refuses_unreachable_daemon_without_killing_metadata_pid(self) -> None:
        args = argparse.Namespace(runtime="/untrusted/runtime", timeout=0.1, wait=0.1, force=True)
        connect_error = groundstation_cli.DaemonConnectError("daemon is not connectable")
        with mock.patch.object(groundstation_cli, "daemon_status_payload", return_value={"connectable": False}), mock.patch.object(
            groundstation_cli, "daemon_request", side_effect=connect_error
        ), mock.patch.object(groundstation_cli.os, "kill") as kill:
            with self.assertRaises(groundstation_cli.DaemonConnectError):
                groundstation_cli.cmd_daemon_stop(args)
            kill.assert_not_called()

    def test_force_restart_does_not_bypass_authenticated_stop(self) -> None:
        args = argparse.Namespace(force=True)
        with mock.patch.object(groundstation_cli, "cmd_daemon_stop", side_effect=groundstation_cli.DaemonConnectError("no IPC")), mock.patch.object(
            groundstation_cli, "cmd_daemon_start"
        ) as start:
            with self.assertRaises(groundstation_cli.DaemonConnectError):
                groundstation_cli.cmd_daemon_restart(args)
            start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
