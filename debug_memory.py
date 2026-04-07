"""Diagnostic script to identify memory leak in layout_detector.py.

Usage:
    python debug_memory.py --image <path_to_image>

Processes the image through the layout detector and uses tracemalloc
to identify what holds the ~60MB per document.
"""

import argparse
import gc
import os
import sys
import tracemalloc
from PIL import Image
from glmocr.pipeline import Pipeline

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def format_size(bytes_val: int) -> str:
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.1f} MB"


def main():
    parser = argparse.ArgumentParser(description="Memory leak diagnostic")
    parser.add_argument("--image", type=str, required=True, help="Path to test image")
    parser.add_argument("--iterations", type=int, default=3, help="Number of processing iterations")
    args = parser.parse_args()

    # Load image
    image = Image.open(args.image).convert("RGB")
    print(f"Image size: {image.size}, mode: {image.mode}")

    # Import layout detector
    from glmocr.config import load_config

    config = load_config('./glmocr/config.yaml')
    print(config.pipeline.layout)
    from glmocr.layout.layout_detector import PPDocLayoutDetector

    detector = PPDocLayoutDetector(config.pipeline.layout)
    detector.start()

    # print(f"Device: {detector._device}")
    pipeline = Pipeline(config.pipeline)
    pipeline.start()

    # Start tracemalloc
    tracemalloc.start(25)  # Store up to 25 frames per allocation

    import psutil

    process = psutil.Process(os.getpid())

    for iteration in range(args.iterations):
        print(f"\n{'#'*70}")
        print(f"  ITERATION {iteration + 1}/{args.iterations}")
        print(f"{'#'*70}")

        # Memory before
        mem_before = process.memory_info().rss
        print(f"  RSS before: {format_size(mem_before)}")

        # Take snapshot before
        snapshot_before = tracemalloc.take_snapshot()

        messages = [{"role": "user", "content": []}]
        # for _ in range(10):
        messages[0]["content"].append({"type": "image_url", "image_url": {"url": './code.pdf'}})

        request_data = {"messages": messages}
        # Process
        # res = list(
        #     pipeline.process(
        #         request_data,
        #         save_layout_visualization=False,
        #         return_base64=True,
        #     )
        # )
        # print(res)
        results, vis_images = detector.process(
            [image],
            save_visualization=True,
            global_start_idx=0,
            use_polygon=False,
        )

        # Take snapshot after process() returns
        snapshot_after_process = tracemalloc.take_snapshot()
        mem_after_process = process.memory_info().rss
        print(
            f"  RSS after process(): {format_size(mem_after_process)} "
            f"(delta: +{format_size(mem_after_process - mem_before)})"
        )

        # Print diff: what process() allocated
        # print_top_diff(
        #     snapshot_before, snapshot_after_process, f"Iteration {iteration+1}: process() allocations", limit=20
        # )

        # Now delete results and check if memory is freed
        del results
        del vis_images

        # Force garbage collection
        # gc.collect()

        # # Take snapshot after cleanup
        # snapshot_after_cleanup = tracemalloc.take_snapshot()
        # mem_after_cleanup = process.memory_info().rss
        # print(
        #     f"  RSS after cleanup: {format_size(mem_after_cleanup)} "
        #     f"(delta from before: +{format_size(mem_after_cleanup - mem_before)})"
        # )

        # Print diff: what's still alive after cleanup
        # print_top_diff(
        #     snapshot_before,
        #     snapshot_after_cleanup,
        #     f"Iteration {iteration+1}: SURVIVING allocations after gc.collect()",
        #     limit=20,
        # )

        # Check PyTorch allocator
        check_pytorch_allocator()

        # Find large objects
        # find_large_objects()

        # Clear tracemalloc statistics for next iteration
        tracemalloc.clear_traces()

    # Cleanup
    # detector.stop()
    tracemalloc.stop()

    # Final memory check
    gc.collect()
    mem_final = process.memory_info().rss
    print(f"\n{'='*70}")
    print(f"  FINAL RSS: {format_size(mem_final)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
