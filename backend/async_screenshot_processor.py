"""
Async Screenshot Processor for WFH Agent
Handles screenshot compression, encryption, and upload in background workers
Prevents UI blocking and improves performance
"""

import os
import time
import queue
import threading
import multiprocessing
from typing import Optional, Dict, Callable, Any
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScreenshotTask:
    """Represents a screenshot processing task"""
    task_id: str
    image_path: str
    emp_id: int
    timestamp: str
    task_type: str  # 'compress', 'encrypt', 'upload', 'all'
    priority: int = 5  # 1 (highest) to 10 (lowest)
    metadata: Dict[str, Any] = None
    callback: Optional[Callable] = None


class AsyncScreenshotProcessor:
    """
    Async processor for screenshot operations using worker pools
    Prevents blocking main thread during I/O and CPU-intensive operations
    """

    def __init__(self,
                 max_workers: int = 4,
                 use_multiprocessing: bool = True,
                 log_callback: Optional[Callable] = None):
        """
        Initialize async screenshot processor

        Args:
            max_workers: Maximum number of worker threads/processes
            use_multiprocessing: Use ProcessPoolExecutor for CPU-intensive tasks
            log_callback: Optional logging function
        """
        self.max_workers = max_workers
        self.use_multiprocessing = use_multiprocessing
        self.log = log_callback or self._default_log

        # Task queue with priority support
        self.task_queue = queue.PriorityQueue()
        self.results = {}
        self.active_tasks = {}

        # Thread-safe counters
        self._task_counter = 0
        self._counter_lock = threading.Lock()

        # Worker pools
        self.io_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='screenshot-io')

        if use_multiprocessing:
            # Use ProcessPoolExecutor for CPU-intensive compression/encryption
            self.cpu_executor = ProcessPoolExecutor(max_workers=max(2, max_workers // 2))
        else:
            self.cpu_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='screenshot-cpu')

        # Start worker thread
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name='screenshot-worker')
        self.worker_thread.start()

        self.log(f"AsyncScreenshotProcessor initialized: {max_workers} workers, multiprocessing={use_multiprocessing}")

    def _default_log(self, message: str):
        """Default logging function"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [AsyncScreenshot] {message}")

    def _get_task_id(self) -> str:
        """Generate unique task ID"""
        with self._counter_lock:
            self._task_counter += 1
            return f"task_{self._task_counter}_{int(time.time() * 1000)}"

    def submit_task(self,
                   image_path: str,
                   emp_id: int,
                   timestamp: str,
                   task_type: str = 'all',
                   priority: int = 5,
                   metadata: Optional[Dict] = None,
                   callback: Optional[Callable] = None) -> str:
        """
        Submit a screenshot processing task

        Args:
            image_path: Path to screenshot file
            emp_id: Employee ID
            timestamp: Timestamp string
            task_type: Type of processing ('compress', 'encrypt', 'upload', 'all')
            priority: Task priority (1=highest, 10=lowest)
            metadata: Additional metadata
            callback: Optional callback function called with (task_id, result, error)

        Returns:
            Task ID for tracking
        """
        task_id = self._get_task_id()

        task = ScreenshotTask(
            task_id=task_id,
            image_path=image_path,
            emp_id=emp_id,
            timestamp=timestamp,
            task_type=task_type,
            priority=priority,
            metadata=metadata or {},
            callback=callback
        )

        # Add to priority queue (lower priority number = higher priority)
        self.task_queue.put((priority, task_id, task))
        self.active_tasks[task_id] = {'status': 'queued', 'task': task}

        self.log(f"Task {task_id} queued: {task_type} for {os.path.basename(image_path)}")
        return task_id

    def _worker_loop(self):
        """Main worker loop that processes tasks from queue"""
        while self.running:
            try:
                # Get task from queue (blocks with timeout)
                priority, task_id, task = self.task_queue.get(timeout=1.0)

                if task_id not in self.active_tasks:
                    continue

                # Update status
                self.active_tasks[task_id]['status'] = 'processing'
                self.log(f"Processing task {task_id}: {task.task_type}")

                # Submit to appropriate executor based on task type
                if task.task_type in ('compress', 'encrypt'):
                    # CPU-intensive - use CPU pool
                    future = self.cpu_executor.submit(self._process_task, task)
                else:
                    # I/O-intensive - use I/O pool
                    future = self.io_executor.submit(self._process_task, task)

                # Handle completion
                future.add_done_callback(lambda f: self._handle_completion(task_id, f))

            except queue.Empty:
                continue
            except Exception as e:
                self.log(f"Worker loop error: {e}")

    def _process_task(self, task: ScreenshotTask) -> Dict[str, Any]:
        """
        Process a screenshot task

        Args:
            task: ScreenshotTask to process

        Returns:
            Result dictionary
        """
        try:
            start_time = time.time()

            if task.task_type == 'compress':
                result = self._compress_screenshot(task)
            elif task.task_type == 'encrypt':
                result = self._encrypt_screenshot(task)
            elif task.task_type == 'upload':
                result = self._upload_screenshot(task)
            elif task.task_type == 'all':
                # Compress, encrypt, then upload
                compress_result = self._compress_screenshot(task)
                if compress_result['success']:
                    task.image_path = compress_result['output_path']
                    encrypt_result = self._encrypt_screenshot(task)
                    if encrypt_result['success']:
                        task.image_path = encrypt_result['output_path']
                        result = self._upload_screenshot(task)
                        result['compressed'] = True
                        result['encrypted'] = True
                    else:
                        result = encrypt_result
                else:
                    result = compress_result
            else:
                result = {'success': False, 'error': f'Unknown task type: {task.task_type}'}

            elapsed = time.time() - start_time
            result['elapsed_time'] = round(elapsed, 3)
            result['task_id'] = task.task_id

            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'task_id': task.task_id
            }

    def _compress_screenshot(self, task: ScreenshotTask) -> Dict[str, Any]:
        """Compress screenshot"""
        try:
            from screenshot_crypto import ScreenshotCrypto

            # Use crypto module's compression without encryption
            crypto = ScreenshotCrypto()
            img_data, metadata = crypto._process_image(
                task.image_path,
                compress=True,
                max_size=(1920, 1080),
                quality=75
            )

            # Write compressed image
            output_path = task.image_path.replace('.png', '_compressed.jpg')
            with open(output_path, 'wb') as f:
                f.write(img_data)

            return {
                'success': True,
                'output_path': output_path,
                'metadata': metadata
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _encrypt_screenshot(self, task: ScreenshotTask) -> Dict[str, Any]:
        """Encrypt screenshot"""
        try:
            from screenshot_crypto import ScreenshotCrypto

            crypto = ScreenshotCrypto()
            output_path, metadata = crypto.encrypt_screenshot(
                task.image_path,
                compress=True
            )

            return {
                'success': True,
                'output_path': output_path,
                'metadata': metadata
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _upload_screenshot(self, task: ScreenshotTask) -> Dict[str, Any]:
        """Upload screenshot (placeholder - actual upload logic in api_sync)"""
        try:
            # This will be called by api_sync module
            # For now, just simulate upload delay
            time.sleep(0.1)  # Simulate network delay

            return {
                'success': True,
                'message': 'Upload completed (simulated)',
                'file': os.path.basename(task.image_path)
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _handle_completion(self, task_id: str, future):
        """Handle task completion"""
        try:
            result = future.result()
            error = None
        except Exception as e:
            result = None
            error = str(e)
            self.log(f"Task {task_id} failed: {error}")

        # Update task status
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]['task']
            self.active_tasks[task_id]['status'] = 'completed' if result and result.get('success') else 'failed'
            self.active_tasks[task_id]['result'] = result
            self.active_tasks[task_id]['error'] = error

            # Call callback if provided
            if task.callback:
                try:
                    task.callback(task_id, result, error)
                except Exception as e:
                    self.log(f"Callback error for task {task_id}: {e}")

            # Store result
            self.results[task_id] = {
                'result': result,
                'error': error,
                'completed_at': time.time()
            }

            # Log completion
            if result and result.get('success'):
                elapsed = result.get('elapsed_time', 0)
                self.log(f"Task {task_id} completed in {elapsed}s")
            else:
                self.log(f"Task {task_id} failed: {error}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a task"""
        return self.active_tasks.get(task_id)

    def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get result of a completed task"""
        return self.results.get(task_id)

    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Wait for a task to complete

        Args:
            task_id: Task ID to wait for
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            Result dictionary
        """
        start_time = time.time()

        while True:
            status = self.get_task_status(task_id)

            if not status:
                return {'success': False, 'error': 'Task not found'}

            if status['status'] in ('completed', 'failed'):
                return self.get_task_result(task_id) or {'success': False, 'error': 'No result'}

            if timeout and (time.time() - start_time) > timeout:
                return {'success': False, 'error': 'Timeout waiting for task'}

            time.sleep(0.1)

    def get_queue_size(self) -> int:
        """Get number of queued tasks"""
        return self.task_queue.qsize()

    def get_active_count(self) -> int:
        """Get number of active (queued + processing) tasks"""
        return len([t for t in self.active_tasks.values() if t['status'] in ('queued', 'processing')])

    def shutdown(self, wait: bool = True):
        """
        Shutdown the processor

        Args:
            wait: Whether to wait for running tasks to complete
        """
        self.log("Shutting down AsyncScreenshotProcessor...")
        self.running = False

        # Shutdown executors
        self.io_executor.shutdown(wait=wait)
        self.cpu_executor.shutdown(wait=wait)

        # Wait for worker thread
        if wait and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)

        self.log("AsyncScreenshotProcessor shutdown complete")

    def get_stats(self) -> Dict[str, Any]:
        """Get processor statistics"""
        return {
            'queue_size': self.get_queue_size(),
            'active_tasks': self.get_active_count(),
            'total_tasks': len(self.active_tasks),
            'completed_tasks': len(self.results),
            'max_workers': self.max_workers,
            'multiprocessing': self.use_multiprocessing
        }


# Convenience function for quick screenshot processing
def process_screenshot_async(image_path: str,
                            emp_id: int,
                            timestamp: str,
                            processor: Optional[AsyncScreenshotProcessor] = None,
                            callback: Optional[Callable] = None) -> str:
    """
    Quick function to process screenshot asynchronously

    Args:
        image_path: Path to screenshot
        emp_id: Employee ID
        timestamp: Timestamp string
        processor: Optional existing processor (creates new one if None)
        callback: Optional completion callback

    Returns:
        Task ID
    """
    if processor is None:
        processor = AsyncScreenshotProcessor(max_workers=2)

    return processor.submit_task(
        image_path=image_path,
        emp_id=emp_id,
        timestamp=timestamp,
        task_type='all',
        callback=callback
    )


if __name__ == '__main__':
    # Test the async processor
    print("Async Screenshot Processor Test")
    print("=" * 50)

    processor = AsyncScreenshotProcessor(max_workers=4, use_multiprocessing=False)

    print(f"Processor initialized")
    print(f"Stats: {processor.get_stats()}")

    # Test task submission (would need actual screenshot for full test)
    # task_id = processor.submit_task('test.png', 1, '20250101_120000', 'compress')
    # print(f"Submitted task: {task_id}")

    print("\nReady for async screenshot processing!")

    # Keep alive for testing
    import time
    time.sleep(2)
    processor.shutdown()
