"""
Tests for native .xlsx requirements-document extraction
(structifact.discover.extract_text_from_xlsx), and its wiring into
`structifact discover` alongside the existing .md/.txt path.

A real .xlsx requirements document is a *raw workbook a person
typed into*, not a structured spec file (that's adapters/excel.py,
a completely different contract) -- so these fixtures are built with
openpyxl directly rather than pandas' structured writer, to mirror
what a real one looks like: a header row, freeform notes outside any
table, and a blank row a naive reader could trip over.
"""

import os

import pytest

openpyxl = pytest.importorskip("openpyxl")

from structifact.cli import discover
from structifact.discover import extract_text_from_xlsx
from structifact.llm import FakeLLMClient


def _write_workbook(path):
    wb = openpyxl.Workbook()

    hdr = wb.active
    hdr.title = "ORD_HDR"
    hdr.append(["Column", "Desc", "Dim or Meas", "Datatype"])
    hdr.append(["order_id", "Order ID", "Dim", "Varchar(10)"])
    hdr.append([None, None, None, None])  # blank row -- must not crash or appear as content
    hdr.append(["order_total", "Total order amount", "Meas", "Decimal(9,2)"])

    notes = wb.create_sheet("Notes")
    notes.append(["Must join on customer_id to get region."])

    empty = wb.create_sheet("Unused")  # entirely blank sheet -- must be skipped

    wb.save(path)
    return str(path)


# ---------------------------------------------------------------------
# extract_text_from_xlsx
# ---------------------------------------------------------------------

def test_extracts_header_row_and_data_rows(tmp_path):
    path = _write_workbook(tmp_path / "req.xlsx")
    text = extract_text_from_xlsx(path)

    assert "Column | Desc | Dim or Meas | Datatype" in text
    assert "order_id | Order ID | Dim | Varchar(10)" in text
    assert "order_total | Total order amount | Meas | Decimal(9,2)" in text


def test_labels_each_sheet_by_name(tmp_path):
    path = _write_workbook(tmp_path / "req.xlsx")
    text = extract_text_from_xlsx(path)

    assert "## Sheet: ORD_HDR" in text
    assert "## Sheet: Notes" in text
    assert "Must join on customer_id to get region." in text


def test_blank_row_is_skipped_not_rendered_as_empty_cells(tmp_path):
    path = _write_workbook(tmp_path / "req.xlsx")
    text = extract_text_from_xlsx(path)

    assert " |  | " not in text


def test_entirely_blank_sheet_is_omitted(tmp_path):
    path = _write_workbook(tmp_path / "req.xlsx")
    text = extract_text_from_xlsx(path)

    assert "## Sheet: Unused" not in text


def test_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_text_from_xlsx("/no/such/path/req.xlsx")


# ---------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------

RESPONSE = """\
dataset: ord_hdr
fields:
  - name: order_id
    description: Order ID
    role: dimension
    type: varchar(10)
  - name: order_total
    description: Total order amount
    role: measure
    type: decimal(9,2)
unresolved_notes:
  - "Must join on customer_id to get region."
"""


class _Args:
    def __init__(self, spec, output=None, ai=False, yes=False, sample_size=100):
        self.spec = spec
        self.output = output
        self.ai = ai
        self.yes = yes
        self.sample_size = sample_size


def test_xlsx_input_dispatches_to_requirements_path(tmp_path):
    spec = _write_workbook(tmp_path / "req.xlsx")
    fake = FakeLLMClient(canned_response=RESPONSE)
    output_path = str(tmp_path / "out.yml")
    args = _Args(spec=spec, output=output_path, ai=True, yes=True)

    discover(args, ai_client=fake)

    assert len(fake.prompts_received) == 1
    assert "order_id" in fake.prompts_received[0]

    written = open(output_path).read()
    assert "ord_hdr" in written
    assert "customer_id" in written


def test_xlsx_input_without_ai_makes_no_request(tmp_path):
    spec = _write_workbook(tmp_path / "req.xlsx")
    fake = FakeLLMClient(canned_response=RESPONSE)
    args = _Args(spec=spec, ai=False)

    discover(args, ai_client=fake)

    assert fake.prompts_received == []


def test_xlsx_missing_file_reports_cleanly(tmp_path, capsys):
    args = _Args(spec=str(tmp_path / "nope.xlsx"), ai=True, yes=True)

    result = discover(args, ai_client=FakeLLMClient(canned_response=RESPONSE))

    assert result is False
    assert "File not found" in capsys.readouterr().out


def test_xlsx_without_excel_extra_reports_clean_message(tmp_path, monkeypatch, capsys):
    spec = _write_workbook(tmp_path / "req.xlsx")
    args = _Args(spec=spec, ai=True, yes=True)

    def _boom(_path):
        raise ImportError("pandas not installed")

    monkeypatch.setattr("structifact.cli.extract_text_from_xlsx", _boom)

    result = discover(args, ai_client=FakeLLMClient(canned_response=RESPONSE))

    assert result is False
    assert "excel" in capsys.readouterr().out
