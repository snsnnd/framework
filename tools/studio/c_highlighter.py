"""Simple C syntax highlighter for EFW Studio."""

from __future__ import annotations

import re
from typing import Any

import importlib.util

if importlib.util.find_spec("PyQt6") is not None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
    QT_LIB = "PyQt6"
elif importlib.util.find_spec("PyQt5") is not None:
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
    QT_LIB = "PyQt5"
else:
    QSyntaxHighlighter = object
    QT_LIB = "missing"


class CHighlighter(QSyntaxHighlighter):
    """Simple C/C++ syntax highlighter."""
    
    def __init__(self, parent: QTextDocument | None = None):
        super().__init__(parent)
        self.highlighting_rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._setup_rules()
    
    def _setup_rules(self) -> None:
        """Setup highlighting rules for C syntax."""
        
        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#C678DD"))  # Purple
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            "auto", "break", "case", "char", "const", "continue", "default", "do",
            "double", "else", "enum", "extern", "float", "for", "goto", "if",
            "inline", "int", "long", "register", "restrict", "return", "short",
            "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
            "unsigned", "void", "volatile", "while", "_Bool", "_Complex", "_Imaginary",
            # EFW specific
            "efw_status_t", "uint8_t", "uint16_t", "uint32_t", "int8_t", "int16_t", "int32_t",
            "size_t", "bool",
        ]
        for word in keywords:
            pattern = re.compile(r'\b' + word + r'\b')
            self.highlighting_rules.append((pattern, keyword_format))
        
        # Preprocessor
        preprocessor_format = QTextCharFormat()
        preprocessor_format.setForeground(QColor("#E06C75"))  # Red
        preprocessor_format.setFontWeight(QFont.Weight.Bold)
        preprocessor_pattern = re.compile(r'^\s*#\s*\w+')
        self.highlighting_rules.append((preprocessor_pattern, preprocessor_format))
        
        # EFW macros
        efw_macro_format = QTextCharFormat()
        efw_macro_format.setForeground(QColor("#E5C07B"))  # Yellow
        efw_macro_format.setFontWeight(QFont.Weight.Bold)
        efw_macros = [
            "EFW_OK", "EFW_ERR_INVALID", "EFW_ERR_NOT_FOUND", "EFW_ERR_FULL",
            "EFW_ERR_IO", "EFW_ERR_ALREADY_EXISTS", "EFW_ERR_RANGE",
            "EFW_ENABLE_", "EFW_MAX_", "EFW_UNUSED",
            "GENERATED_BODY", "UPROPERTY", "UFUNCTION",
        ]
        for macro in efw_macros:
            pattern = re.compile(r'\b' + macro + r'\w*\b')
            self.highlighting_rules.append((pattern, efw_macro_format))
        
        # Function calls
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#61AFEF"))  # Blue
        function_pattern = re.compile(r'\b([a-zA-Z_]\w*)\s*(?=\()')
        self.highlighting_rules.append((function_pattern, function_format))
        
        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#D19A66"))  # Orange
        number_pattern = re.compile(r'\b[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?[fFlLuU]*\b')
        self.highlighting_rules.append((number_pattern, number_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#98C379"))  # Green
        string_pattern = re.compile(r'"[^"\\]*(\\.[^"\\]*)*"')
        self.highlighting_rules.append((string_pattern, string_format))
        
        # Single line comments
        single_comment_format = QTextCharFormat()
        single_comment_format.setForeground(QColor("#5C6370"))  # Gray
        single_comment_format.setFontItalic(True)
        single_comment_pattern = re.compile(r'//[^\n]*')
        self.highlighting_rules.append((single_comment_pattern, single_comment_format))
        
        # Types (EFW structs and common types)
        type_format = QTextCharFormat()
        type_format.setForeground(QColor("#E5C07B"))  # Yellow
        type_format.setFontWeight(QFont.Weight.Bold)
        types = [
            "efw_hal_ops_t", "efw_sensor_ops_t", "efw_actuator_ops_t",
            "efw_algo_ops_t", "efw_module_ops_t", "efw_sm_context_t",
            "efw_state_def_t", "efw_sm_transition_t", "efw_pid_t",
            "efw_pid_input_t", "efw_pid_output_t", "efw_motor_cmd_t",
            "efw_line_tracking_data_t", "efw_line_follower_t",
            "efw_ringbuf_t", "efw_queue_t", "efw_stack_t",
            "efw_error_t", "app_gpio_pin_t", "app_pwm_channel_t",
        ]
        for type_name in types:
            pattern = re.compile(r'\b' + type_name + r'\b')
            self.highlighting_rules.append((pattern, type_format))
        
        # Multi-line comment state
        self.multi_line_comment_format = QTextCharFormat()
        self.multi_line_comment_format.setForeground(QColor("#5C6370"))
        self.multi_line_comment_format.setFontItalic(True)
        self.comment_start = re.compile(r'/\*')
        self.comment_end = re.compile(r'\*/')
    
    def highlightBlock(self, text: str) -> None:
        """Apply highlighting rules to a block of text."""
        # Apply single-line rules
        for pattern, fmt in self.highlighting_rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, fmt)
        
        # Handle multi-line comments
        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            match = self.comment_start.search(text)
            start_index = match.start() if match else -1
        
        while start_index >= 0:
            end_match = self.comment_end.search(text, start_index + 2)
            if end_match:
                length = end_match.end() - start_index
                self.setFormat(start_index, length, self.multi_line_comment_format)
                start_match = self.comment_start.search(text, end_match.end())
                start_index = start_match.start() if start_match else -1
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start_index
                self.setFormat(start_index, length, self.multi_line_comment_format)
                break
