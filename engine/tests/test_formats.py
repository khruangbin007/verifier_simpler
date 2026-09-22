"""test_formats.py - the front door of reading, held to the review of 18 September 2026.

That review found that the reader rarely got a file wrong in a way that SHOWED. It got it wrong in
a way that closed the content account, produced units and looked fine: a spreadsheet read as a
Word file and lost whole, a legacy .doc decoded into pages of mojibake, a folder that stopped the
run with a traceback. The one sentence it ended on was that almost every problem was a failure
to be honest about failure.

Every finding is pinned here, by number, so that none of them can come back quietly. Each file
is either read with its structure or refused in plain words with a next step. Nothing in between.
"""
import io
import os
import tarfile
import unittest
import zipfile

import helpers
import core
import reading
def zipped(members):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return raw.getvalue()


def spreadsheet():
    import openpyxl
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Floors"
    for row in (("Segment", "Floor"), ("Retail", 0.15), ("Corporate", 0.25)):
        sheet.append(row)
    raw = io.BytesIO()
    book.save(raw)
    return raw.getvalue()


def read(name, data):
    chunks, result = helpers.chunks_of(name, data)
    return chunks, result, result.records["content_accounts"][0]


def refused_reason(chunks):
    return next((chunk["not_read_reason"] for chunk in chunks if chunk["not_read_reason"]), "")


class Finding1TheRunIsNeverStoppedByAFile(unittest.TestCase):
    """A subfolder, a ZIP where a tarball was expected, and an encrypted PDF each ended the run
    with a traceback: no Output.xlsx, nothing at all. R2 says nothing stops a run."""

    def test_a_subfolder_is_walked_into_and_its_files_read(self):
        folder = helpers.scratch()
        os.makedirs(os.path.join(folder, "chapters"))
        with open(os.path.join(folder, "chapters", "one.xml"), "w") as handle:
            handle.write("<doc><para>Inside a subfolder.</para></doc>")
        found, _ = core.input_files(folder)
        self.assertEqual([os.path.relpath(path, folder) for path in found], [os.path.join("chapters", "one.xml")])

    def test_an_encrypted_pdf_is_named_and_the_run_goes_on(self):
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.encrypt("secret")
        raw = io.BytesIO()
        writer.write(raw)
        chunks, result, _ = read("locked.pdf", raw.getvalue())
        self.assertIn("password", refused_reason(chunks))
        self.assertTrue(any("Not read: locked.pdf" in message for message in result.messages))

    def test_a_package_delivered_as_a_zip_is_read(self):
        path = os.path.join(helpers.scratch(), "model.zip")
        with open(path, "wb") as handle:
            handle.write(zipped({"pkg/DESCRIPTION": "Package: pkg\nVersion: 0.1\n",
                                 "pkg/R/k.R": "capital_k <- function(pd) pd * 12.5\n"}))
        result = reading.read_package(helpers.context_for({"package": [path]}))
        kinds = [core.to_plain(unit)["kind"] for unit in result.records["model_units"]]
        self.assertIn("Function", kinds, "the R code inside a ZIP should be parsed")

    def test_a_damaged_package_is_named_and_the_run_goes_on(self):
        path = os.path.join(helpers.scratch(), "broken.tar.gz")
        with open(path, "wb") as handle:
            handle.write(b"\x1f\x8b\x08 not really a tarball")
        result = reading.read_package(helpers.context_for({"package": [path]}))
        self.assertIn("could not be opened", result.messages[0])
        self.assertIn("damaged", result.messages[0])

    def test_a_package_put_in_unpacked_is_read_as_a_package(self):
        source = helpers.scratch()
        os.makedirs(os.path.join(source, "pkg", "R"))
        with open(os.path.join(source, "pkg", "DESCRIPTION"), "w") as handle:
            handle.write("Package: pkg\nVersion: 0.1\n")
        with open(os.path.join(source, "pkg", "R", "k.R"), "w") as handle:
            handle.write("capital_k <- function(pd) pd * 12.5\n")
        found, _ = core.input_files(source)
        context = helpers.context_for({"package": found})
        context.options["inputs"]["roots"] = {"package": source}
        result = reading.read_package(context)
        kinds = [core.to_plain(unit)["kind"] for unit in result.records["model_units"]]
        self.assertIn("Function", kinds, "a package's source folder is a package")

    def test_a_reader_that_fails_on_one_file_leaves_the_others_read(self):
        folder = helpers.scratch()
        good, bad = os.path.join(folder, "a.xml"), os.path.join(folder, "b.pdf")
        with open(good, "w") as handle:
            handle.write("<doc><para>The good file.</para></doc>")
        with open(bad, "wb") as handle:
            handle.write(b"%PDF-1.4 and then nothing a PDF reader can use")
        result = reading.read_methodology(helpers.context_for({"methodology": [good, bad]}))
        texts = [chunk.text for chunk in result.records["chunks_canon"]]
        self.assertIn("The good file.", texts)


class Finding2EveryZipIsLookedInside(unittest.TestCase):
    """PK\\x03\\x04 begins a Word file, a spreadsheet, a slide deck, an OpenDocument file, an
    e-book and a plain ZIP. All were sent to the Word reader, failed, and closed their account."""

    def test_each_kind_of_zip_is_told_apart(self):
        self.assertEqual(core.detect_format(zipped({"word/document.xml": "<w/>"})), "docx")
        self.assertEqual(core.detect_format(spreadsheet()), "xlsx")
        self.assertEqual(core.detect_format(zipped({"ppt/presentation.xml": "<p/>"})), "pptx")
        self.assertEqual(core.detect_format(zipped({"content.xml": "<c/>", "mimetype": "x"})), "odf")
        self.assertEqual(core.detect_format(zipped({"META-INF/container.xml": "<c/>"})), "epub")
        self.assertEqual(core.detect_format(zipped({"notes.txt": "x"})), "zip")

    def test_a_spreadsheet_is_read_sheet_by_sheet_as_tables(self):
        chunks, _, account = read("method.xlsx", spreadsheet())
        tables = [chunk for chunk in chunks if chunk["kind"] == "Table"]
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["heading_chain"], ["Floors"], "each sheet is a heading over its table")
        self.assertIn("Retail", tables[0]["text"])
        self.assertTrue(account["closed"], account["what unaccounted"])

    def test_a_slide_deck_is_refused_with_a_next_step(self):
        chunks, _, account = read("deck.pptx", zipped({"ppt/presentation.xml": "<p>x</p>"}))
        reason = refused_reason(chunks)
        self.assertIn("slide deck", reason)
        self.assertIn("save it as PDF", reason, "a refusal says what to do next")
        self.assertEqual(account["not read"], 1)


class Finding2bTheAccountNoLongerClosesOverNothing(unittest.TestCase):
    """The ledger could not count what it could not open, so a file whose reader found nothing
    and said nothing closed its account over nothing. That was the one place the identity held
    while everything was lost."""

    def test_a_large_file_that_yields_no_text_and_says_nothing_opens_the_account(self):
        import core as reading
        found = core.account("empty.docx", [], [], file_bytes=40000)
        self.assertTrue(found["vacuous"])
        self.assertFalse(found["closed"])
        self.assertTrue(any("probably not been opened" in line for line in core.account_lines(found)))

    def test_a_file_refused_by_name_is_not_called_vacuous(self):
        import core as reading
        atoms = [core.atom("whole file not read", "deck.pptx", "")]
        found = core.account("deck.pptx", atoms, [{"kind": "Paragraph", "text": "", "not_read_reason": "a slide deck"}],
                                file_bytes=40000)
        self.assertFalse(found["vacuous"], "a refusal in plain words is honest, not silent")
        self.assertTrue(found["closed"])

    def test_a_small_empty_file_is_simply_empty(self):
        import core as reading
        self.assertFalse(core.account("tiny.txt", [], [], file_bytes=12)["vacuous"])


class Finding3BinaryIsNeverDecodedAsText(unittest.TestCase):
    """A legacy .doc, a picture and Thumbs.db were decoded as Latin-1 and shown as paragraphs of
    mojibake, which were then searched, judged and linked against."""

    def test_each_binary_kind_is_refused_and_none_becomes_text(self):
        for name, data, says in (("legacy.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 200, "old Microsoft Office"),
                                 ("scan.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 300, "picture"),
                                 ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 300, "picture"),
                                 ("blob.bin", b"\x00\x01\x02\x03" * 100, "binary data")):
            chunks, _, _ = read(name, data)
            self.assertEqual([chunk["text"] for chunk in chunks], [""], "%s must not become text" % name)
            self.assertIn(says, refused_reason(chunks), name)

    def test_text_with_the_odd_control_character_is_still_text(self):
        self.assertEqual(core.detect_format(b"A line.\x0cA new page.\nAnother line."), "text")


class Finding4MarkdownKeepsItsStructure(unittest.TestCase):
    TEXT = (b"# Capital\n\nThe buffer is **three** per cent of `exposure`.\n\n## Floors\n\n"
            b"Floors apply:\n\n- retail: 0.15\n- corporate: 0.25\n\n"
            b"| Segment | Floor |\n|---|---|\n| Retail | 0.15 |\n\n```r\nk <- pd * 12.5\n```\n")

    def test_headings_become_headings_at_their_depth(self):
        chunks, _, _ = read("rules.md", self.TEXT)
        chains = {tuple(chunk["heading_chain"]) for chunk in chunks}
        self.assertIn(("Capital",), chains)
        self.assertIn(("Capital", "Floors"), chains)

    def test_a_table_is_a_table_and_code_is_kept(self):
        chunks, _, _ = read("rules.md", self.TEXT)
        self.assertEqual(sum(1 for chunk in chunks if chunk["kind"] == "Table"), 1)
        self.assertTrue(any("k <- pd * 12.5" in chunk["text"] for chunk in chunks), "fenced code is kept word for word")

    def test_inline_marks_are_taken_away_and_nothing_is_lost_or_added(self):
        chunks, _, account = read("rules.md", self.TEXT)
        text = " ".join(chunk["text"] for chunk in chunks)
        self.assertIn("The buffer is three per cent of exposure.", text)
        self.assertNotIn("**", text)
        self.assertTrue(account["closed"], (account["what unaccounted"], account["what injected"]))

    def test_a_markdown_file_that_opens_with_an_html_comment_is_still_markdown(self):
        """A wiki export begins with a comment. It starts with "<", which looked like XML; the
        name decides for Markdown, and the comment - a note to an editor, not what the document
        says - is left out by one rule in the markup and in the words, so the account closes."""
        data = b"<!-- exported from the wiki on Monday -->\n# Capital\n\nThe buffer is three per cent.\n"
        self.assertEqual(core.detect_format(data, "rules.md"), "markdown")
        chunks, _, account = read("rules.md", data)
        self.assertEqual([(chunk["heading_chain"], chunk["text"]) for chunk in chunks],
                         [(["Capital"], "The buffer is three per cent.")])
        self.assertTrue(account["closed"], (account["what unaccounted"], account["what injected"]))

    def test_an_underscore_inside_a_name_survives(self):
        chunks, _, _ = read("names.md", b"# Symbols\n\nThe parameter rho_a is the asset correlation.\n")
        self.assertIn("rho_a", " ".join(chunk["text"] for chunk in chunks))


class Finding5DelimitedRowsAreATable(unittest.TestCase):
    def test_a_csv_in_a_document_corner_is_read_as_a_table(self):
        chunks, _, account = read("floors.csv", b"segment,floor\nRetail,0.15\nCorporate,0.25\n")
        self.assertEqual([chunk["kind"] for chunk in chunks], ["Table"])
        self.assertEqual(chunks[0]["table"]["header"], ["segment", "floor"])
        self.assertTrue(account["closed"], account["what unaccounted"])

    def test_prose_that_happens_to_hold_commas_is_not_a_table(self):
        self.assertEqual(core.detect_format(b"First, the buffer.\nSecond, the floor, which is lower.\n", "notes.txt"), "text")


class Finding6RtfAndLatexLeaveTheirMarkupBehind(unittest.TestCase):
    def test_rtf_keeps_its_words_and_loses_its_control_words(self):
        data = rb"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0 The buffer is three per cent.\par A floor of one per cent applies.\par}"
        chunks, _, account = read("method.rtf", data)
        texts = [chunk["text"] for chunk in chunks]
        self.assertEqual(texts, ["The buffer is three per cent.", "A floor of one per cent applies."])
        self.assertTrue(account["closed"])

    def test_latex_sections_are_headings_and_its_preamble_is_not_content(self):
        data = (rb"\documentclass{article}\usepackage{amsmath}\begin{document}\section{Capital}The buffer is three per cent."
                rb"\subsection{Floors}\begin{itemize}\item retail\item corporate\end{itemize}\end{document}")
        chunks, _, account = read("rules.tex", data)
        self.assertIn(("Capital", "Floors"), {tuple(chunk["heading_chain"]) for chunk in chunks})
        self.assertNotIn("article", " ".join(chunk["text"] for chunk in chunks))
        self.assertTrue(account["closed"], account["what unaccounted"])


class Finding7ANonRPackageIsNamedAsOne(unittest.TestCase):
    def test_a_python_model_is_named_rather_than_silently_unverifiable(self):
        path = os.path.join(helpers.scratch(), "model.tar.gz")
        with tarfile.open(path, "w:gz") as archive:
            data = b"def capital_k(pd):\n    return pd * 12.5\n"
            info = tarfile.TarInfo("m/capital.py")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        result = reading.read_package(helpers.context_for({"package": [path]}))
        said = " ".join(result.messages)
        self.assertIn("does not look like an R package", said)
        self.assertIn("nothing in them can be linked or checked", said)

    def test_an_r_package_draws_no_such_note(self):
        path = os.path.join(helpers.scratch(), "model.zip")
        with open(path, "wb") as handle:
            handle.write(zipped({"pkg/DESCRIPTION": "Package: pkg\n", "pkg/R/k.R": "k <- 1\n"}))
        result = reading.read_package(helpers.context_for({"package": [path]}))
        self.assertFalse([message for message in result.messages if "R package" in message])


class Finding8OnlyDocumentsAreRead(unittest.TestCase):
    def test_editor_and_system_leavings_are_named_and_not_read(self):
        folder = helpers.scratch()
        for name, data in (("method.xml", b"<doc/>"), ("~$method.docx", b"\x00"), ("Thumbs.db", b"\x00"),
                           ("desktop.ini", b"x"), (".DS_Store", b"\x00")):
            with open(os.path.join(folder, name), "wb") as handle:
                handle.write(data)
        found, skipped = core.input_files(folder)
        self.assertEqual([os.path.basename(path) for path in found], ["method.xml"])
        self.assertEqual(sorted(name for name, _ in skipped), sorted(["~$method.docx", "Thumbs.db", "desktop.ini", ".DS_Store"]))

    def test_the_support_folder_of_a_saved_web_page_is_not_read_as_documents(self):
        folder = helpers.scratch()
        os.makedirs(os.path.join(folder, "method_files"))
        with open(os.path.join(folder, "method.htm"), "w") as handle:
            handle.write("<html><body><p>The page.</p></body></html>")
        with open(os.path.join(folder, "method_files", "style.css"), "w") as handle:
            handle.write("p { margin: 0 }")
        found, skipped = core.input_files(folder)
        self.assertEqual([os.path.basename(path) for path in found], ["method.htm"])
        self.assertEqual(skipped, [("method_files", "the support folder of a saved web page")])

    def test_a_folder_that_is_not_a_web_pages_support_folder_is_read(self):
        folder = helpers.scratch()
        os.makedirs(os.path.join(folder, "annex_files"))
        with open(os.path.join(folder, "annex_files", "a.xml"), "w") as handle:
            handle.write("<doc/>")
        found, _ = core.input_files(folder)
        self.assertEqual(len(found), 1, "only a folder beside a page of the same name is the page's")


class Finding9TheAnalystIsToldWhatEachFileWasReadAs(unittest.TestCase):
    def test_the_step_says_what_it_read_each_file_as_and_what_it_did_not_read(self):
        folder = helpers.scratch()
        paths = []
        for name, data in (("a.xml", b"<doc><para>One.</para></doc>"), ("b.md", b"# Two\n\nText.\n"),
                           ("c.pptx", zipped({"ppt/presentation.xml": "<p/>"}))):
            paths.append(os.path.join(folder, name))
            with open(paths[-1], "wb") as handle:
                handle.write(data)
        result = reading.read_methodology(helpers.context_for({"methodology": paths}))
        said = "\n".join(result.messages)
        self.assertIn("Read as: 1 Markdown, 1 XML.", said)
        self.assertIn("Not read: c.pptx - the file is a slide deck", said)
        for message in result.messages:
            self.assertEqual(helpers.banned_wording(message), "", message)


class Finding10TextHeldOnlyAsTextIsCounted(unittest.TestCase):
    """R5 found that a package member with no reader is fully accounted for and still unusable.
    The account now says how much of the package is held only as running text."""

    def test_the_package_account_counts_lines_held_only_as_running_text(self):
        import fixture_package
        path = os.path.join(helpers.scratch(), "oddly_0.1.0.tar.gz")
        with open(path, "wb") as handle:
            handle.write(fixture_package.tarball())
        result = reading.read_package(helpers.context_for({"package": [path]}))
        account = result.records["content_accounts"][0]
        self.assertGreater(account["held as text only"], 0)
        rows = [row["value"] for row in result.records["package_info"][0]["rows"] if row["item"] == "content account"]
        self.assertTrue(any("held only as running text" in row for row in rows), rows)


class SvgPicturesAreReadByTheirOwnText(unittest.TestCase):
    """An SVG holds its text as text, so a chart's labels and a table drawn as a picture are read
    without guesswork: every word comes from a <text> element. Where a methodology's XML refers
    to an SVG beside it, the figure takes the picture's content as its own."""

    CHART = (b'<svg xmlns="http://www.w3.org/2000/svg"><title>Figure 2</title>'
             b'<text x="150" y="20">Discount rate against number of parcels</text><text x="5" y="30">10%</text><text x="5" y="170">0%</text></svg>')
    TABLE = (b'<svg xmlns="http://www.w3.org/2000/svg"><desc>Floors by segment</desc>'
             b'<text x="10" y="20">Segment</text><text x="120" y="20">Floor</text>'
             b'<text x="10" y="40">Retail</text><text x="120" y="40">0.15</text>'
             b'<text x="10" y="60">Corporate</text><text x="120" y="60"><tspan>0.25</tspan></text></svg>')

    def test_an_svg_is_told_from_xml_by_its_root(self):
        self.assertEqual(core.detect_format(self.CHART, "chart.svg"), "svg")
        self.assertEqual(core.detect_format(b'<?xml version="1.0"?><doc><para>x</para></doc>', "m.txt"), "xml")

    def test_text_standing_in_a_grid_is_a_table_and_labels_are_a_figure(self):
        chunks, _, account = read("floors.svg", self.TABLE)
        self.assertEqual([chunk["kind"] for chunk in chunks], ["Table"])
        self.assertEqual(chunks[0]["table"]["rows"], [["Retail", "0.15"], ["Corporate", "0.25"]])
        self.assertTrue(account["closed"])
        chunks, _, account = read("chart.svg", self.CHART)
        self.assertEqual([chunk["kind"] for chunk in chunks], ["Figure"])
        self.assertIn("Discount rate against number of parcels", chunks[0]["text"])
        self.assertTrue(account["closed"])

    def test_a_figure_in_the_xml_takes_the_svg_beside_it(self):
        folder = helpers.scratch()
        with open(os.path.join(folder, "floors.svg"), "wb") as handle:
            handle.write(self.TABLE)
        with open(os.path.join(folder, "method.txt"), "w", encoding="utf-8") as handle:
            handle.write('<doc><section num="1."><title>Floors</title><para>See Table 3.</para>'
                         '<figure src="floors.svg"><caption>Table 3. Floors by segment</caption></figure>'
                         '<figure src="missing.svg"><caption>Figure 9. Not there</caption></figure>'
                         '<figure src="../floors.svg"><caption>Figure 10. Outside</caption></figure></section></doc>')
        result = reading.read_methodology(helpers.context_for({"methodology": [os.path.join(folder, "method.txt")]}))
        units = [core.to_plain(unit) for unit in result.records["chunks_canon"]]
        table = [unit for unit in units if unit["kind"] == "Table"][0]
        self.assertEqual(table["caption"], "Table 3. Floors by segment", "the document's own caption wins")
        self.assertEqual(table["table"]["rows"], [["Retail", "0.15"], ["Corporate", "0.25"]])
        figures = [unit for unit in units if unit["kind"] == "Figure"]
        self.assertEqual(sorted(unit["caption"] for unit in figures), ["Figure 10. Outside", "Figure 9. Not there"],
                         "a missing picture and a path that climbs out stay plain figures")
        self.assertTrue(result.records["content_accounts"][0]["closed"])


if __name__ == "__main__":
    unittest.main()
