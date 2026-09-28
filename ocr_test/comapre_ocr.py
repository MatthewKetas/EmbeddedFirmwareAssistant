"""Convert one file with OCR on and off, time both, and show what differs.

Usage:  py compare_ocr2.py esp32_datasheet_en.pdf
Writes: <name>.ocr_on.md and <name>.ocr_off.md in the current folder.
"""
import difflib
import importlib.util
import os
import sys
import time
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

try:
    from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
except ImportError:
    from docling.datamodel.pipeline_options import AcceleratorDevice, AcceleratorOptions


def make_ocr_options():
    """Build RapidOcrOptions using only the fields this Docling version has."""
    fields = set(RapidOcrOptions.model_fields)
    kwargs = {}
    if "backend" in fields and importlib.util.find_spec("onnxruntime"):
        kwargs["backend"] = "onnxruntime"   # faster than torch on CPU
    if "bitmap_area_threshold" in fields:
        kwargs["bitmap_area_threshold"] = 0.10
    print(f"  OCR options used: {kwargs or 'defaults'}")
    return RapidOcrOptions(**kwargs)


def run(path: Path, do_ocr: bool) -> tuple[str, float]:
    opts = PdfPipelineOptions()
    opts.do_ocr = do_ocr
    opts.do_table_structure = True
    if do_ocr:
        opts.ocr_options = make_ocr_options()
    opts.accelerator_options = AcceleratorOptions(
        num_threads=os.cpu_count() or 8, device=AcceleratorDevice.AUTO
    )
    conv = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    t = time.time()
    md = conv.convert(str(path)).document.export_to_markdown()
    return md, time.time() - t


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: py compare_ocr2.py <file.pdf>")
    path = Path(sys.argv[1]).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        sys.exit(f"Not found: {path}")

    print(f"Docling fields available on RapidOcrOptions: {sorted(RapidOcrOptions.model_fields)}\n")

    results, times = {}, {}
    for label, flag in (("ocr_off", False), ("ocr_on", True)):
        print(f"Converting with OCR {'ON' if flag else 'OFF'} ...")
        md, secs = run(path, flag)
        results[label], times[label] = md, secs
        out = Path.cwd() / f"{path.stem}.{label}.md"
        out.write_text(md, encoding="utf-8")
        print(f"  {secs:.1f}s, {len(md):,} chars -> {out.name}\n")

    off, on = results["ocr_off"].splitlines(), results["ocr_on"].splitlines()
    diff = [l for l in difflib.unified_diff(off, on, lineterm="", n=0)
            if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]

    print(f"OCR off: {times['ocr_off']:.1f}s | OCR on: {times['ocr_on']:.1f}s "
          f"| OCR cost: {times['ocr_on'] - times['ocr_off']:.1f}s")
    print(f"Differing lines: {len(diff)}")
    if not diff:
        print("Identical output: OCR adds nothing here, so DO_OCR = False is safe.")
    else:
        print("First differences (+ = only with OCR, - = only without):")
        for l in diff[:40]:
            print("  " + l[:160])
        print("\nOpen the two .md files side by side for the full picture.")


if __name__ == "__main__":
    main()