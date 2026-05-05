from __future__ import annotations
"""Desktop GUI for the offline preprocessing pipeline.

Tk widgets must be updated on the main thread, so the pipeline runs in a worker
thread and reports progress back through a queue.
"""

import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, Tk, filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from aoi360_pipeline.rebuild_runtime_assets import (
    derive_runtime_build_paths,
    find_repo_root,
    rebuild_runtime_assets,
)
from aoi360_pipeline.runtime_environment import inspect_torch_runtime


class PreprocessGuiApp:
    """Thin presentation layer over the rebuild pipeline."""

    STAGE_ORDER = ("extract", "detect", "build")
    STAGE_WEIGHTS = {
        "extract": 0.2,
        "detect": 0.5,
        "build": 0.3,
    }
    POLL_INTERVAL_MS = 120

    def __init__(self) -> None:
        self.repo_root = find_repo_root(Path(__file__).resolve())
        self.event_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.runtime_summary = inspect_torch_runtime()

        self.root = Tk()
        self.root.title("AOI360 Offline Preprocessing")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        default_width = min(1280, max(980, screen_width - 120))
        default_height = min(900, max(720, screen_height - 140))
        self.root.geometry(f"{default_width}x{default_height}")
        self.root.minsize(980, 700)

        default_video_path = self.repo_root / "data" / "input_videos" / "video_360.mp4"
        self.video_path_var = StringVar(value=str(default_video_path))
        self.text_prompt_var = StringVar(value="person. face. bottle. screen. product.")
        self.include_labels_var = StringVar(value="")
        self.every_n_frames_var = IntVar(value=10)
        self.frame_step_var = IntVar(value=30)
        self.output_width_var = IntVar(value=1024)
        self.output_height_var = IntVar(value=512)
        self.detection_batch_size_var = IntVar(value=self.runtime_summary.recommended_batch_size)
        self.detection_max_width_var = IntVar(value=1920)
        self.detection_max_height_var = IntVar(value=960)
        self.detection_preload_workers_var = IntVar(value=self.runtime_summary.recommended_preload_workers)
        self.yaw_offset_var = DoubleVar(value=0.0)
        self.min_confidence_var = DoubleVar(value=0.35)
        self.box_threshold_var = DoubleVar(value=0.35)
        self.text_threshold_var = DoubleVar(value=0.25)
        self.clean_var = BooleanVar(value=True)

        self.frames_dir_var = StringVar()
        self.detections_csv_var = StringVar()
        self.maps_dir_var = StringVar()
        self.metadata_dir_var = StringVar()
        self.manifest_path_var = StringVar()
        self.runtime_pack_path_var = StringVar()

        self.current_stage_label_var = StringVar(value="Idle")
        self.current_stage_detail_var = StringVar(value="Select a video and start preprocessing.")
        self.overall_progress_label_var = StringVar(value="Overall progress: 0%")
        self.runtime_label_var = StringVar(value=f"Runtime: {self.runtime_summary.short_label}")

        self.stage_progress_var = DoubleVar(value=0.0)
        self.overall_progress_var = DoubleVar(value=0.0)

        self.start_button: ttk.Button | None = None

        self._build_ui()
        self._refresh_output_paths()
        self.video_path_var.trace_add("write", lambda *_: self._refresh_output_paths())
        self.root.after(self.POLL_INTERVAL_MS, self._process_worker_events)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        header = ttk.Frame(self.root, padding=(14, 12, 14, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text="AOI360 Preprocessing Console",
            font=("Segoe UI", 15, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Select a 360 video, launch the offline pipeline, and follow the rebuild step by step.",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(
            header,
            textvariable=self.runtime_label_var,
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

        controls = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        controls.grid(row=1, column=0, sticky="nsew")
        controls.columnconfigure(0, weight=3)
        controls.columnconfigure(1, weight=2)
        controls.rowconfigure(0, weight=1)

        left_column = ttk.Frame(controls)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_column.columnconfigure(1, weight=1)

        ttk.Label(left_column, text="Video").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(left_column, textvariable=self.video_path_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Button(left_column, text="Browse...", command=self._browse_video).grid(row=0, column=2, sticky="ew", padx=(8, 0), pady=(0, 8))

        ttk.Label(left_column, text="Prompt").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(left_column, textvariable=self.text_prompt_var).grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Label(left_column, text="Include labels").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(left_column, textvariable=self.include_labels_var).grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)

        self._add_spinbox(left_column, "Extract every N frames", self.every_n_frames_var, 3, from_=1, to=1000)
        self._add_spinbox(left_column, "Export AOI keyframe step", self.frame_step_var, 4, from_=1, to=5000)
        self._add_spinbox(left_column, "Output width", self.output_width_var, 5, from_=64, to=8192, increment=64)
        self._add_spinbox(left_column, "Output height", self.output_height_var, 6, from_=64, to=4096, increment=64)
        self._add_spinbox(left_column, "Detection batch size", self.detection_batch_size_var, 7, from_=1, to=64)
        self._add_spinbox(left_column, "Detection max width", self.detection_max_width_var, 8, from_=0, to=8192, increment=64)
        self._add_spinbox(left_column, "Detection max height", self.detection_max_height_var, 9, from_=0, to=4096, increment=64)
        self._add_spinbox(left_column, "Detection preload workers", self.detection_preload_workers_var, 10, from_=0, to=32)
        self._add_spinbox(left_column, "Yaw offset (deg)", self.yaw_offset_var, 11, from_=-360.0, to=360.0, increment=1.0)
        self._add_spinbox(left_column, "Min confidence", self.min_confidence_var, 12, from_=0.0, to=1.0, increment=0.05)
        self._add_spinbox(left_column, "Box threshold", self.box_threshold_var, 13, from_=0.0, to=1.0, increment=0.05)
        self._add_spinbox(left_column, "Text threshold", self.text_threshold_var, 14, from_=0.0, to=1.0, increment=0.05)

        ttk.Checkbutton(
            left_column,
            text="Clean previously generated outputs before rebuilding",
            variable=self.clean_var,
        ).grid(row=15, column=0, columnspan=3, sticky="w", pady=(10, 0))

        right_column = ttk.LabelFrame(controls, text="Resolved output layout", padding=10)
        right_column.grid(row=0, column=1, sticky="nsew")
        right_column.columnconfigure(1, weight=1)
        self._add_output_row(right_column, "Frames", self.frames_dir_var, 0)
        self._add_output_row(right_column, "Detections CSV", self.detections_csv_var, 1)
        self._add_output_row(right_column, "AOI maps", self.maps_dir_var, 2)
        self._add_output_row(right_column, "AOI metadata", self.metadata_dir_var, 3)
        self._add_output_row(right_column, "Manifest", self.manifest_path_var, 4)
        self._add_output_row(right_column, "Runtime pack", self.runtime_pack_path_var, 5)

        actions = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        actions.grid(row=2, column=0, sticky="nsew")
        actions.columnconfigure(0, weight=1)
        actions.rowconfigure(4, weight=1)

        button_row = ttk.Frame(actions)
        button_row.grid(row=0, column=0, sticky="ew")
        self.start_button = ttk.Button(button_row, text="Start preprocessing", command=self._start_preprocessing)
        self.start_button.pack(side="left")
        ttk.Button(button_row, text="Open input videos", command=self._open_input_video_folder).pack(side="left", padx=(8, 0))

        ttk.Label(actions, textvariable=self.current_stage_label_var, font=("Segoe UI", 11, "bold")).grid(
            row=1, column=0, sticky="w", pady=(12, 4)
        )
        ttk.Label(actions, textvariable=self.current_stage_detail_var).grid(row=2, column=0, sticky="w")

        progress_frame = ttk.Frame(actions)
        progress_frame.grid(row=3, column=0, sticky="ew", pady=(12, 12))
        progress_frame.columnconfigure(0, weight=1)

        ttk.Progressbar(progress_frame, variable=self.stage_progress_var, maximum=100.0).grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.overall_progress_label_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Progressbar(progress_frame, variable=self.overall_progress_var, maximum=100.0).grid(row=2, column=0, sticky="ew", pady=(4, 0))

        logs_frame = ttk.LabelFrame(actions, text="Pipeline logs", padding=8)
        logs_frame.grid(row=4, column=0, sticky="nsew")
        logs_frame.columnconfigure(0, weight=1)
        logs_frame.rowconfigure(0, weight=1)

        self.logs_text = ScrolledText(logs_frame, wrap="word", height=16, font=("Consolas", 9))
        self.logs_text.grid(row=0, column=0, sticky="nsew")
        self.logs_text.configure(state="disabled")

    def _add_spinbox(self, parent, label: str, variable, row: int, *, from_, to, increment=1) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Spinbox(
            parent,
            textvariable=variable,
            from_=from_,
            to=to,
            increment=increment,
            width=12,
        ).grid(row=row, column=1, sticky="w", pady=4)

    def _add_output_row(self, parent, label: str, variable: StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", pady=(0, 8))
        ttk.Entry(parent, textvariable=variable, state="readonly").grid(row=row, column=1, sticky="ew", pady=(0, 8))

    def _browse_video(self) -> None:
        initial_dir = self.repo_root / "data" / "input_videos"
        selected_path = filedialog.askopenfilename(
            title="Select a 360 video",
            initialdir=str(initial_dir if initial_dir.exists() else self.repo_root),
            filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm"),
                ("All files", "*.*"),
            ],
        )
        if selected_path:
            self.video_path_var.set(selected_path)

    def _open_input_video_folder(self) -> None:
        input_videos_dir = self.repo_root / "data" / "input_videos"
        input_videos_dir.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.startfile(input_videos_dir)  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - desktop shell integration
            messagebox.showinfo("Open folder", f"Could not open the folder automatically.\n\n{exc}")

    def _refresh_output_paths(self) -> None:
        # Resolve paths from the selected video every time so the UI always shows
        # the real layout Unity will later consume.
        video_path = self.video_path_var.get().strip()
        if not video_path:
            return

        resolved = derive_runtime_build_paths(video_path=video_path, repo_root=self.repo_root)
        self.frames_dir_var.set(str(resolved.frames_dir))
        self.detections_csv_var.set(str(resolved.detections_csv))
        self.maps_dir_var.set(str(resolved.output_maps_dir))
        self.metadata_dir_var.set(str(resolved.output_metadata_dir))
        self.manifest_path_var.set(str(resolved.manifest_path))
        self.runtime_pack_path_var.set(str(resolved.runtime_pack_path))

    def _start_preprocessing(self) -> None:
        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showinfo("Pipeline running", "The preprocessing pipeline is already running.")
            return

        video_path = Path(self.video_path_var.get().strip())
        if not video_path.exists():
            messagebox.showerror("Missing video", f"The selected video does not exist:\n\n{video_path}")
            return

        self._reset_progress()
        self._append_log("[gui] Starting offline preprocessing pipeline.")
        self._set_running_state(True)

        self.worker_thread = threading.Thread(target=self._run_pipeline_worker, daemon=True)
        self.worker_thread.start()

    def _run_pipeline_worker(self) -> None:
        # Keep the heavy work outside the UI thread to avoid freezing the window
        # during model loading, frame extraction, or AOI export.
        try:
            include_labels = [
                value.strip()
                for value in self.include_labels_var.get().split(",")
                if value.strip()
            ]
            summary = rebuild_runtime_assets(
                video_path=self.video_path_var.get().strip(),
                text_prompt=self.text_prompt_var.get().strip(),
                every_n_frames=int(self.every_n_frames_var.get()),
                frame_step=int(self.frame_step_var.get()),
                output_width=int(self.output_width_var.get()),
                output_height=int(self.output_height_var.get()),
                detection_batch_size=int(self.detection_batch_size_var.get()),
                detection_max_width=int(self.detection_max_width_var.get()) or None,
                detection_max_height=int(self.detection_max_height_var.get()) or None,
                detection_preload_workers=int(self.detection_preload_workers_var.get()),
                yaw_offset_degrees=float(self.yaw_offset_var.get()),
                min_confidence=float(self.min_confidence_var.get()),
                box_threshold=float(self.box_threshold_var.get()),
                text_threshold=float(self.text_threshold_var.get()),
                include_labels=include_labels or None,
                clean=bool(self.clean_var.get()),
                progress_callback=self._queue_progress_event,
                log_callback=self._queue_log_event,
            )
            self.event_queue.put(("done", summary))
        except Exception:
            self.event_queue.put(("error", traceback.format_exc()))

    def _queue_progress_event(self, stage: str, current: int, total: int, message: str) -> None:
        self.event_queue.put(("progress", (stage, current, total, message)))

    def _queue_log_event(self, message: str) -> None:
        self.event_queue.put(("log", message))

    def _process_worker_events(self) -> None:
        # Tkinter is single-threaded. The worker only pushes plain events and
        # the main loop is the only place that touches widgets.
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "log":
                self._append_log(str(payload))
            elif event_type == "progress":
                stage, current, total, message = payload  # type: ignore[misc]
                self._apply_progress(stage, int(current), int(total), str(message))
            elif event_type == "done":
                self._handle_success(payload)  # type: ignore[arg-type]
            elif event_type == "error":
                self._handle_error(str(payload))

        self.root.after(self.POLL_INTERVAL_MS, self._process_worker_events)

    def _apply_progress(self, stage: str, current: int, total: int, message: str) -> None:
        stage_title = {
            "extract": "Stage 1/3 - Frame extraction",
            "detect": "Stage 2/3 - Grounding DINO detection",
            "build": "Stage 3/3 - AOI sequence export",
            "done": "Completed",
        }.get(stage, stage)

        safe_total = max(total, 1)
        stage_fraction = max(0.0, min(1.0, current / safe_total))
        self.stage_progress_var.set(stage_fraction * 100.0)
        self.current_stage_label_var.set(stage_title)
        self.current_stage_detail_var.set(message)

        if stage == "done":
            overall_fraction = 1.0
        else:
            completed_weight = 0.0
            for stage_name in self.STAGE_ORDER:
                if stage_name == stage:
                    break
                completed_weight += self.STAGE_WEIGHTS[stage_name]

            stage_weight = self.STAGE_WEIGHTS.get(stage, 0.0)
            overall_fraction = completed_weight + (stage_weight * stage_fraction)

        overall_percentage = max(0.0, min(100.0, overall_fraction * 100.0))
        self.overall_progress_var.set(overall_percentage)
        self.overall_progress_label_var.set(f"Overall progress: {overall_percentage:.1f}%")

    def _handle_success(self, summary: dict[str, object]) -> None:
        self._apply_progress("done", 1, 1, "Runtime assets rebuilt successfully.")
        self._append_log("[gui] Offline preprocessing pipeline completed.")
        self._append_log(f"[gui] AOI keyframes written: {summary['written_count']} / {summary['keyframe_count']}")
        self._append_log(f"[gui] Manifest: {summary['manifest_path']}")
        self._set_running_state(False)
        messagebox.showinfo(
            "Preprocessing completed",
            (
                "Runtime assets are ready.\n\n"
                f"AOI keyframes written: {summary['written_count']} / {summary['keyframe_count']}\n"
                f"Manifest: {summary['manifest_path']}"
            ),
        )

    def _handle_error(self, traceback_text: str) -> None:
        self._append_log("[gui] Pipeline failed.")
        self._append_log(traceback_text)
        self.current_stage_label_var.set("Pipeline failed")
        self.current_stage_detail_var.set("Check the logs below to see what went wrong.")
        self._set_running_state(False)
        messagebox.showerror("Preprocessing failed", "The pipeline stopped with an error. Check the logs for details.")

    def _set_running_state(self, is_running: bool) -> None:
        if self.start_button is not None:
            self.start_button.configure(state="disabled" if is_running else "normal")

    def _reset_progress(self) -> None:
        self.stage_progress_var.set(0.0)
        self.overall_progress_var.set(0.0)
        self.current_stage_label_var.set("Queued")
        self.current_stage_detail_var.set("Preparing the pipeline...")
        self.overall_progress_label_var.set("Overall progress: 0.0%")
        self.logs_text.configure(state="normal")
        self.logs_text.delete("1.0", "end")
        self.logs_text.configure(state="disabled")

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs_text.configure(state="normal")
        self.logs_text.insert("end", f"[{timestamp}] {message}\n")
        self.logs_text.see("end")
        self.logs_text.configure(state="disabled")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    PreprocessGuiApp().run()


if __name__ == "__main__":
    main()
