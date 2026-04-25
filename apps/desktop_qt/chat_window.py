from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from apps.desktop_qt.api_client import APIClient
from apps.desktop_qt.recorder import AudioRecorder
from apps.desktop_qt.user_identity import DesktopIdentityStore


class Worker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(f"{exc}\n\n{traceback.format_exc()}")


class ChatBubble(QFrame):
    def __init__(self, speaker: str, text: str, align: str, bubble_color: str, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        name_label = QLabel(speaker)
        name_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #5b5347;")
        layout.addWidget(name_label)

        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_label.setStyleSheet("font-size: 14px; line-height: 1.5; color: #1f1f1f;")
        layout.addWidget(text_label)

        self.setStyleSheet(
            f"""
            QFrame {{
                background: {bubble_color};
                border: 1px solid rgba(60, 60, 60, 0.08);
                border-radius: 16px;
            }}
            """
        )

        self.setMaximumWidth(420 if align == "right" else 560)


class ChatWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("AIAgent Desktop Panel")
        self.resize(1480, 920)

        self.identity_store = DesktopIdentityStore()
        self.user_id, self.username = self._load_or_create_identity()
        self.api_base_url = "http://127.0.0.1:8000"

        self.api_client = APIClient(self.api_base_url)
        self.recorder = AudioRecorder()

        self.current_thread: QThread | None = None
        self.current_worker: Worker | None = None
        self.current_task_name: str = ""

        self._build_ui()
        self._append_system_message(
            f"桌面端已启动，当前身份为 {self.username}。现在可以直接观察 state / planner / llm 的调试输出。"
        )
        self._set_status("就绪")
        self.run_startup_check()

    def closeEvent(self, event) -> None:
        try:
            if self.current_thread is not None and self.current_thread.isRunning():
                self.current_thread.quit()
                self.current_thread.wait(3000)
        except Exception:
            pass

        try:
            self.api_client.close()
        except Exception:
            pass

        super().closeEvent(event)

    def _load_or_create_identity(self) -> tuple[str, str]:
        identity = self.identity_store.load_identity()
        if identity is not None:
            return identity.user_id, identity.username

        username, ok = QInputDialog.getText(self, "输入昵称", "请输入你的名字：")
        if not ok or not username.strip():
            username = "Guest"

        identity = self.identity_store.create_identity(username.strip())
        return identity.user_id, identity.username

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(18, 18, 18, 18)
        outer_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([920, 720])

        outer_layout.addWidget(splitter)

        root.setStyleSheet(
            """
            QWidget {
                background: #efe6d8;
                font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
            }
            QFrame#leftPanel, QFrame#rightPanel {
                background: rgba(255, 252, 247, 0.92);
                border: 1px solid #d8ccbf;
                border-radius: 22px;
            }
            """
        )

    def _build_left_panel(self) -> QWidget:
        left_panel = QFrame()
        left_panel.setObjectName("leftPanel")

        layout = QVBoxLayout(left_panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title_label = QLabel("Yzl 对话窗口")
        title_label.setStyleSheet("font-size: 28px; font-weight: 800; color: #2f241f;")
        layout.addWidget(title_label)

        self.identity_label = QLabel(
            f"当前用户：{self.username}\n用户ID：{self.user_id}\n服务端：{self.api_base_url}"
        )
        self.identity_label.setStyleSheet("font-size: 13px; color: #6f6258; line-height: 1.6;")
        layout.addWidget(self.identity_label)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.NoFrame)
        self.chat_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(8, 8, 8, 8)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll, 1)

        self.status_label = QLabel("状态：就绪")
        self.status_label.setStyleSheet("font-size: 13px; color: #705e50;")
        layout.addWidget(self.status_label)

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("输入你想说的话……")
        self.input_edit.setMinimumHeight(130)
        self.input_edit.setMaximumHeight(220)
        layout.addWidget(self.input_edit)

        input_button_row = QHBoxLayout()
        input_button_row.setSpacing(10)

        self.send_button = QPushButton("发送消息")
        self.send_button.clicked.connect(self.send_text_message)
        input_button_row.addWidget(self.send_button)

        self.start_record_button = QPushButton("开始录音")
        self.start_record_button.clicked.connect(self.start_voice_recording)
        input_button_row.addWidget(self.start_record_button)

        self.stop_record_button = QPushButton("结束录音")
        self.stop_record_button.clicked.connect(self.stop_voice_recording)
        self.stop_record_button.setDisabled(True)
        input_button_row.addWidget(self.stop_record_button)

        layout.addLayout(input_button_row)
        return left_panel

    def _build_right_panel(self) -> QWidget:
        right_panel = QFrame()
        right_panel.setObjectName("rightPanel")

        layout = QVBoxLayout(right_panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setFrameShape(QFrame.NoFrame)
        tools_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        tools_content = QWidget()
        tools_layout = QVBoxLayout(tools_content)
        tools_layout.setContentsMargins(0, 0, 4, 0)
        tools_layout.setSpacing(12)

        control_card = self._build_section_card("快捷控制")
        control_layout = control_card.layout()

        control_grid = QGridLayout()
        control_grid.setHorizontalSpacing(10)
        control_grid.setVerticalSpacing(10)

        self.startup_check_button = QPushButton("启动自检")
        self.startup_check_button.clicked.connect(self.run_startup_check)
        control_grid.addWidget(self.startup_check_button, 0, 0)

        self.refresh_button = QPushButton("刷新状态")
        self.refresh_button.clicked.connect(self.refresh_state)
        control_grid.addWidget(self.refresh_button, 0, 1)

        self.pause_button = QPushButton("暂停对话")
        self.pause_button.clicked.connect(self.pause_dialogue)
        control_grid.addWidget(self.pause_button, 1, 0)

        self.resume_button = QPushButton("恢复对话")
        self.resume_button.clicked.connect(self.resume_dialogue)
        control_grid.addWidget(self.resume_button, 1, 1)

        self.interrupt_button = QPushButton("打断播放")
        self.interrupt_button.clicked.connect(self.interrupt_speaking)
        control_grid.addWidget(self.interrupt_button, 2, 0)

        self.reset_context_button = QPushButton("重置上下文")
        self.reset_context_button.clicked.connect(self.reset_context)
        control_grid.addWidget(self.reset_context_button, 2, 1)

        self.clear_memory_button = QPushButton("清空记忆")
        self.clear_memory_button.clicked.connect(self.clear_memory)
        control_grid.addWidget(self.clear_memory_button, 3, 0)

        self.clear_chat_button = QPushButton("清空聊天窗口")
        self.clear_chat_button.clicked.connect(self.clear_chat)
        control_grid.addWidget(self.clear_chat_button, 3, 1)

        control_layout.addLayout(control_grid)
        tools_layout.addWidget(control_card)

        knowledge_card = self._build_section_card("知识库调试")
        knowledge_layout = knowledge_card.layout()

        self.knowledge_query_edit = QTextEdit()
        self.knowledge_query_edit.setPlaceholderText("输入一个问题，测试知识库命中效果……")
        self.knowledge_query_edit.setMinimumHeight(76)
        self.knowledge_query_edit.setMaximumHeight(110)
        knowledge_layout.addWidget(self.knowledge_query_edit)

        knowledge_button_row = QHBoxLayout()
        self.search_knowledge_button = QPushButton("检索知识")
        self.search_knowledge_button.clicked.connect(self.search_knowledge)
        knowledge_button_row.addWidget(self.search_knowledge_button)

        self.rebuild_knowledge_button = QPushButton("重建索引")
        self.rebuild_knowledge_button.clicked.connect(self.rebuild_knowledge)
        knowledge_button_row.addWidget(self.rebuild_knowledge_button)

        knowledge_layout.addLayout(knowledge_button_row)
        tools_layout.addWidget(knowledge_card)

        memory_card = self._build_section_card("记忆检索")
        memory_layout = memory_card.layout()

        self.memory_query_edit = QTextEdit()
        self.memory_query_edit.setPlaceholderText("输入关键词，搜索当前用户的记忆……")
        self.memory_query_edit.setMinimumHeight(76)
        self.memory_query_edit.setMaximumHeight(110)
        memory_layout.addWidget(self.memory_query_edit)

        memory_button_row = QHBoxLayout()
        self.search_memory_button = QPushButton("搜索记忆")
        self.search_memory_button.clicked.connect(self.search_memory)
        memory_button_row.addWidget(self.search_memory_button)

        self.memory_stats_button = QPushButton("记忆统计")
        self.memory_stats_button.clicked.connect(self.load_memory_stats)
        memory_button_row.addWidget(self.memory_stats_button)

        memory_layout.addLayout(memory_button_row)
        tools_layout.addWidget(memory_card)

        state_graph_card = self._build_section_card("State Graph")
        state_graph_layout = state_graph_card.layout()
        self.state_graph_view = QTextEdit()
        self.state_graph_view.setReadOnly(True)
        self.state_graph_view.setMinimumHeight(220)
        state_graph_layout.addWidget(self.state_graph_view)
        tools_layout.addWidget(state_graph_card)

        planner_graph_card = self._build_section_card("Planner Graph")
        planner_graph_layout = planner_graph_card.layout()
        self.planner_graph_view = QTextEdit()
        self.planner_graph_view.setReadOnly(True)
        self.planner_graph_view.setMinimumHeight(220)
        planner_graph_layout.addWidget(self.planner_graph_view)
        tools_layout.addWidget(planner_graph_card)

        detail_card = self._build_section_card("LLM / API Detail")
        detail_layout = detail_card.layout()
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        self.detail_view.setMinimumHeight(220)
        detail_layout.addWidget(self.detail_view)
        tools_layout.addWidget(detail_card)

        state_card = self._build_section_card("Runtime Snapshot")
        state_layout = state_card.layout()
        self.state_view = QTextEdit()
        self.state_view.setReadOnly(True)
        self.state_view.setMinimumHeight(220)
        state_layout.addWidget(self.state_view)
        tools_layout.addWidget(state_card)

        tools_layout.addStretch()
        tools_scroll.setWidget(tools_content)
        layout.addWidget(tools_scroll, 1)

        return right_panel

    def _build_section_card(self, title: str) -> QFrame:
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #2f241f;")
        layout.addWidget(title_label)
        return card

    def _set_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}")

    def _append_system_message(self, text: str) -> None:
        self._append_bubble("系统", text, "left", "#ece7df")

    def _append_user_message(self, username: str, text: str) -> None:
        self._append_bubble(username, text, "right", "#dcefff")

    def _append_agent_message(self, text: str) -> None:
        self._append_bubble("Yzl", text, "left", "#f8dcc8")

    def _append_bubble(self, speaker: str, text: str, align: str, color: str) -> None:
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)

        bubble = ChatBubble(speaker=speaker, text=text, align=align, bubble_color=color)

        if align == "right":
            wrapper_layout.addStretch()
            wrapper_layout.addWidget(bubble)
        else:
            wrapper_layout.addWidget(bubble)
            wrapper_layout.addStretch()

        stretch_item = self.chat_layout.takeAt(self.chat_layout.count() - 1)
        self.chat_layout.addWidget(wrapper)
        if stretch_item is not None:
            self.chat_layout.addItem(stretch_item)

        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

    def _set_busy(self, busy: bool) -> None:
        for button in [
            self.send_button,
            self.refresh_button,
            self.pause_button,
            self.resume_button,
            self.interrupt_button,
            self.reset_context_button,
            self.clear_memory_button,
            self.search_knowledge_button,
            self.rebuild_knowledge_button,
            self.search_memory_button,
            self.memory_stats_button,
            self.startup_check_button,
        ]:
            button.setDisabled(busy)

        self.input_edit.setDisabled(busy)

        if self.recorder.is_recording:
            self.start_record_button.setDisabled(True)
            self.stop_record_button.setDisabled(False)
        else:
            self.start_record_button.setDisabled(busy)
            self.stop_record_button.setDisabled(True)

    def _start_worker(self, task_name: str, fn) -> None:
        if self.current_thread is not None and self.current_thread.isRunning():
            QMessageBox.warning(self, "提示", "当前已有任务在执行，请稍后。")
            return

        self.current_task_name = task_name

        thread = QThread(self)
        worker = Worker(fn)

        self.current_thread = thread
        self.current_worker = worker

        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        worker.finished.connect(self._handle_worker_success)
        worker.finished.connect(self._worker_finished)
        worker.error.connect(self._worker_error)

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(self._thread_finished)

        thread.start()

    @Slot(object)
    def _handle_worker_success(self, result: object) -> None:
        task_name = self.current_task_name

        if task_name == "chat":
            self._on_chat_finished(result)
        elif task_name == "voice":
            self._on_voice_finished(result)
        elif task_name == "refresh":
            self._on_refresh_finished(result)
        elif task_name == "startup_check":
            self._on_startup_check_finished(result)
        elif task_name == "pause":
            self._on_action_finished("已暂停对话。", result)
        elif task_name == "resume":
            self._on_action_finished("已恢复对话。", result)
        elif task_name == "interrupt":
            self._on_action_finished("已发送打断指令。", result)
        elif task_name == "reset_context":
            self._on_action_finished("上下文已重置。", result)
        elif task_name == "clear_memory":
            self._on_action_finished("用户记忆已清空。", result)
        elif task_name == "search_knowledge":
            self._on_json_result("知识检索完成。", result)
        elif task_name == "rebuild_knowledge":
            self._on_json_result("知识索引重建完成。", result)
        elif task_name == "search_memory":
            self._on_json_result("记忆搜索完成。", result)
        elif task_name == "memory_stats":
            self._on_json_result("记忆统计已加载。", result)

        self.current_task_name = ""

    @Slot(object)
    def _worker_finished(self, _result: object) -> None:
        if self.current_worker is not None:
            self.current_worker.deleteLater()
            self.current_worker = None

    @Slot(str)
    def _worker_error(self, error_text: str) -> None:
        if self.current_worker is not None:
            self.current_worker.deleteLater()
            self.current_worker = None

        self.current_task_name = ""
        self._set_busy(False)
        self.start_record_button.setDisabled(self.recorder.is_recording)
        self.stop_record_button.setDisabled(not self.recorder.is_recording)
        self._set_status("发生错误")
        QMessageBox.critical(self, "错误", error_text)

    @Slot()
    def _thread_finished(self) -> None:
        if self.current_thread is not None:
            self.current_thread.deleteLater()
            self.current_thread = None

    def send_text_message(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        self._append_user_message(self.username, text)
        self.input_edit.clear()
        self._set_busy(True)
        self._set_status("正在请求回复...")

        self._start_worker(
            "chat",
            lambda: self.api_client.send_chat(
                user_id=self.user_id,
                username=self.username,
                text=text,
            ),
        )

    def start_voice_recording(self) -> None:
        try:
            self.recorder.start_recording()
        except Exception as exc:
            QMessageBox.critical(self, "录音错误", str(exc))
            return

        self.start_record_button.setDisabled(True)
        self.stop_record_button.setDisabled(False)
        self._append_system_message("开始录音，请说话。")
        self._set_status("录音中...")

    def stop_voice_recording(self) -> None:
        try:
            audio_path = self.recorder.stop_recording()
        except Exception as exc:
            self.start_record_button.setDisabled(False)
            self.stop_record_button.setDisabled(True)
            QMessageBox.critical(self, "录音错误", str(exc))
            return

        self.start_record_button.setDisabled(True)
        self.stop_record_button.setDisabled(True)
        self._set_busy(True)
        self._set_status("正在识别语音并生成回复...")

        self._start_worker("voice", lambda: self._run_voice_pipeline(audio_path))

    def _run_voice_pipeline(self, audio_path: str) -> dict:
        asr_result = self.api_client.transcribe_audio(audio_path)
        transcript = str(asr_result.get("transcript", "")).strip()

        if not transcript:
            raise RuntimeError("ASR 没有返回文本。")

        chat_result = self.api_client.send_chat(
            user_id=self.user_id,
            username=self.username,
            text=transcript,
        )

        return {
            "audio_path": audio_path,
            "transcript": transcript,
            "asr_result": asr_result,
            "chat_result": chat_result,
        }

    def run_startup_check(self) -> None:
        self._set_status("正在执行启动自检...")
        self._set_busy(True)
        self._start_worker(
            "startup_check",
            lambda: self.api_client.run_startup_check(self.user_id),
        )

    def refresh_state(self) -> None:
        self._set_status("正在刷新状态...")
        self._set_busy(True)
        self._start_worker(
            "refresh",
            lambda: self.api_client.get_runtime_snapshot(self.user_id),
        )

    def pause_dialogue(self) -> None:
        self._set_status("正在暂停对话...")
        self._set_busy(True)
        self._start_worker("pause", self.api_client.pause_dialogue)

    def resume_dialogue(self) -> None:
        self._set_status("正在恢复对话...")
        self._set_busy(True)
        self._start_worker("resume", self.api_client.resume_dialogue)

    def interrupt_speaking(self) -> None:
        self._set_status("正在打断播放...")
        self._set_busy(True)
        self._start_worker(
            "interrupt",
            lambda: self.api_client.interrupt_voice(reason="desktop_qt_interrupt"),
        )

    def reset_context(self) -> None:
        self._set_status("正在重置上下文...")
        self._set_busy(True)
        self._start_worker("reset_context", self.api_client.reset_context)

    def clear_memory(self) -> None:
        confirm = QMessageBox.question(
            self,
            "确认清空记忆",
            f"确定要清空用户 {self.user_id} 的记忆吗？",
        )
        if confirm != QMessageBox.Yes:
            return

        self._set_status("正在清空记忆...")
        self._set_busy(True)
        self._start_worker(
            "clear_memory",
            lambda: self.api_client.clear_user_memory(self.user_id),
        )

    def clear_chat(self) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.detail_view.clear()
        self.state_view.clear()
        self.state_graph_view.clear()
        self.planner_graph_view.clear()
        self._append_system_message("聊天窗口已清空。")
        self._set_status("就绪")

    def search_knowledge(self) -> None:
        query = self.knowledge_query_edit.toPlainText().strip()
        if not query:
            QMessageBox.information(self, "提示", "请先输入知识检索问题。")
            return

        self._set_status("正在检索知识...")
        self._set_busy(True)
        self._start_worker(
            "search_knowledge",
            lambda: self.api_client.search_knowledge(query=query, top_k=4),
        )

    def rebuild_knowledge(self) -> None:
        self._set_status("正在重建知识索引...")
        self._set_busy(True)
        self._start_worker(
            "rebuild_knowledge",
            lambda: self.api_client.rebuild_knowledge(force_rebuild=True),
        )

    def search_memory(self) -> None:
        query = self.memory_query_edit.toPlainText().strip()
        if not query:
            QMessageBox.information(self, "提示", "请先输入记忆搜索关键词。")
            return

        self._set_status("正在搜索记忆...")
        self._set_busy(True)
        self._start_worker(
            "search_memory",
            lambda: self.api_client.search_user_memory(user_id=self.user_id, query=query, limit=10),
        )

    def load_memory_stats(self) -> None:
        self._set_status("正在加载记忆统计...")
        self._set_busy(True)
        self._start_worker(
            "memory_stats",
            lambda: self.api_client.get_memory_stats(self.user_id),
        )

    def _on_chat_finished(self, result: object) -> None:
        data = dict(result)
        reply = str(data.get("reply", "")).strip()
        self._append_agent_message(reply or "后端没有返回回复。")
        self._update_graph_debug(data)
        self._update_detail_view(data)
        self._set_busy(False)
        self._set_status("就绪")

    def _on_voice_finished(self, result: object) -> None:
        data = dict(result)
        transcript = data["transcript"]
        chat_result = data["chat_result"]

        self._append_user_message(self.username, f"[语音识别] {transcript}")
        reply = str(chat_result.get("reply", "")).strip()
        self._append_agent_message(reply or "后端没有返回回复。")
        self._update_graph_debug(chat_result)
        self._update_detail_view(data)

        self._set_busy(False)
        self.start_record_button.setDisabled(False)
        self.stop_record_button.setDisabled(True)
        self._set_status("就绪")

    def _on_startup_check_finished(self, result: object) -> None:
        data = dict(result)
        self.detail_view.setPlainText(self.api_client.pretty_json(data))
        self.state_view.setPlainText(self.api_client.pretty_json(data))
        self._append_system_message("启动自检完成。")
        self._set_busy(False)
        self._set_status("启动自检完成")

    def _on_refresh_finished(self, result: object) -> None:
        data = dict(result)
        self.state_view.setPlainText(self.api_client.pretty_json(data))
        self._set_busy(False)
        self._set_status("状态已刷新")

    def _on_action_finished(self, message: str, result: object) -> None:
        data = dict(result)
        self._append_system_message(message)
        self.state_view.setPlainText(self.api_client.pretty_json(data))
        self._set_busy(False)
        self._set_status("操作完成")

    def _on_json_result(self, message: str, result: object) -> None:
        data = dict(result)
        self.detail_view.setPlainText(self.api_client.pretty_json(data))
        self._append_system_message(message)
        self._set_busy(False)
        self._set_status("操作完成")

    def _update_graph_debug(self, data: dict) -> None:
        debug = data.get("debug", {})
        state_result = debug.get("state_result", {})
        planner_result = debug.get("planner_result", {})

        self.state_graph_view.setPlainText(
            self.api_client.pretty_json(state_result if isinstance(state_result, dict) else {})
        )
        self.planner_graph_view.setPlainText(
            self.api_client.pretty_json(planner_result if isinstance(planner_result, dict) else {})
        )

    def _update_detail_view(self, data: dict) -> None:
        self.detail_view.setPlainText(self.api_client.pretty_json(data))
