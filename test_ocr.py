import ctypes
import gc
from pathlib import Path
from time import sleep
from typing import List, Union

from glmocr.api import GlmOcr
from glmocr.parser_result import PipelineResult


def parse_files_in_loop(
    file_paths: List[Union[str, Path]],
    output_dir: str = "./output",
    **parser_kwargs,
) -> List[PipelineResult]:
    """Parse a list of files by calling GlmOcr.parse() in a loop.

    Creates a single GlmOcr instance (reuses connection/pipeline) and
    processes each file one by one, saving results to output_dir.

    Args:
        file_paths: List of paths to images or PDFs.
        output_dir: Directory where results will be saved.
        **parser_kwargs: Passed to GlmOcr.__init__ (e.g. api_key, mode).

    Returns:
        List of PipelineResult, one per input file.
    """
    results = []

    with GlmOcr('./conf.yml') as parser:
        sleep(20)
        for idx, file_path in enumerate(file_paths):
            print(f"Parsing: {idx}")
            result = parser.parse(file_path)

    return results


if __name__ == "__main__":
    files = ['./scan.pdf'] * 80

    if not files:
        print("No PDF or PNG files found in current directory.")
    else:
        parse_files_in_loop(
            files,
            output_dir="./output",
            # api_key=os.environ.get("ZHIPU_API_KEY"),
            # mode="maas",
        )
    sleep(15)
    gc.collect()
    print('gc called')
    sleep(15)
    ctypes.CDLL("libc.so.6").malloc_trim(0)
    print('trimmalloc called')
    sleep(60)
