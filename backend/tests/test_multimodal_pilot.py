import csv
import json

import pymupdf
from app.ingestion.inventory import FIELDS, inventory_rows
from app.ingestion.multimodal_pilot import run_multimodal_pilot
from PIL import Image


def test_pilot_exports_image_manifest_and_page_render_without_overwriting(
    tmp_path,
) -> None:
    project_root = tmp_path
    pdf_path = project_root / "Grade 05" / "English" / "representative.pdf"
    pdf_path.parent.mkdir(parents=True)
    picture = tmp_path / "picture.png"
    Image.new("RGB", (80, 60), "blue").save(picture)

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "This readable English page contains sufficient text for the extraction pilot.",
    )
    page.insert_image(pymupdf.Rect(100, 100, 260, 220), filename=str(picture))
    page.draw_rect(pymupdf.Rect(100, 260, 300, 340))
    page.draw_line((200, 260), (200, 340))
    page.draw_line((100, 300), (300, 300))
    page.insert_text((110, 285), "Question")
    page.insert_text((210, 285), "Answer")
    document.save(pdf_path)
    document.close()

    rows, _ = inventory_rows(project_root)
    inventory_path = project_root / "inventory.csv"
    with inventory_path.open("w", encoding="utf-8-sig", newline="") as inventory:
        writer = csv.DictWriter(inventory, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    output_dir = project_root / "data" / "pilot_multimodal_test"
    report = run_multimodal_pilot(
        project_root,
        inventory_path,
        output_dir,
        selected_ids={rows[0]["textbook_id"]},
    )

    with (output_dir / "image_manifest.csv").open(
        encoding="utf-8-sig", newline=""
    ) as manifest:
        images = list(csv.DictReader(manifest))
    assert images
    for image in images:
        assert (output_dir / image["image_path"]).is_file()
        assert int(image["pdf_page_number"]) == 1
        assert image["width_pixels"] == "80"
        assert image["height_pixels"] == "60"
    assert (output_dir / images[0]["page_render_path"]).is_file()
    page_output = output_dir / f"{rows[0]['textbook_id']}.pages.jsonl"
    [page_record] = [
        json.loads(line)
        for line in page_output.read_text(encoding="utf-8").splitlines()
    ]
    assert page_record["pdf_page_number"] == 1
    assert page_record["image_reference_count"] == 1
    ocr_records = (output_dir / "ocr_results.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert ocr_records == []
    assert report["vision_analysis"]["performed"] is False
    sample = json.loads((output_dir / "sample_content.json").read_text(encoding="utf-8"))
    assert sample[0]["tables"]

    try:
        run_multimodal_pilot(
            project_root,
            inventory_path,
            output_dir,
            selected_ids={rows[0]["textbook_id"]},
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("Existing pilot output must not be overwritten.")
