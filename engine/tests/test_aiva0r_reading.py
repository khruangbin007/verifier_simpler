"""test_aiva0r_reading.py - the reading floor, and above all the content account of R13.

A reader may decide HOW a file is sliced. It may not add a word the file does not contain and
it may not lose a word the file does contain. These tests plant a sentence in each of the
places a reader is most likely to walk past, and check that the account either places it or
says out loud that it could not.
"""
import io
import unittest
import zipfile

import helpers
import aiva0r_reading as reading
import aiva1_documents


def plain(chunks):
    return chunks


def account_of(file_name, data, corner="methodology"):
    chunks, result = helpers.chunks_of(file_name, data, corner=corner)
    return result.records["content_accounts"][0], chunks


WORD_MAIN = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def docx_bytes(body_xml, extra=None):
    """A Word file with the given body, and any extra parts (footnotes, headers)."""
    document = ('<?xml version="1.0"?><w:document xmlns:w="%s"><w:body>%s</w:body></w:document>'
                % (WORD_MAIN, body_xml))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
        for name, text in (extra or {}).items():
            archive.writestr(name, text)
    return buffer.getvalue()


def paragraph(text, style=""):
    style_xml = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return '<w:p>%s<w:r><w:t>%s</w:t></w:r></w:p>' % (style_xml, text)


class TokensAndBags(unittest.TestCase):
    """The countable piece is a run without white space, after the normalisation every chunk's
    text goes through - so that folding a list, which joins its items with a space, does not
    look like a change of content."""

    def test_white_space_is_not_counted_and_a_repeated_word_is_counted_twice(self):
        self.assertEqual(reading.tokens("  a   b\n c "), ["a", "b", "c"])
        self.assertEqual(reading.bag("a b a"), {"a": 2, "b": 1})

    def test_taking_away_stops_at_zero_and_never_goes_below(self):
        self.assertEqual(reading.minus({"a": 2, "b": 1}, {"a": 3}), {"b": 1})


class NothingIsLost(unittest.TestCase):
    """A sentence planted where a reader is most likely to walk past it is either in a unit or
    named in the account. It is never silently absent."""

    def test_a_tail_after_an_inline_element_is_counted(self):
        found, chunks = account_of("t.xml", "<doc><para>Before <b>bold</b> after the bold.</para></doc>")
        self.assertEqual(found["unaccounted"], 0, found["what unaccounted"])
        self.assertIn("after", " ".join(chunk["text"] for chunk in chunks))

    def test_an_unknown_tag_keeps_its_words(self):
        found, chunks = account_of("u.xml", "<doc><nobodyknows>A rule nobody anticipated.</nobodyknows></doc>")
        self.assertEqual(found["unaccounted"], 0, found["what unaccounted"])
        self.assertIn("anticipated", " ".join(chunk["text"] for chunk in chunks))

    def test_a_word_only_in_a_docx_footnote_is_never_absent_without_a_word(self):
        footnotes = ('<?xml version="1.0"?><w:footnotes xmlns:w="%s"><w:footnote w:id="1"><w:p><w:r>'
                     '<w:t>The footnote says spifflicated.</w:t></w:r></w:p></w:footnote></w:footnotes>' % WORD_MAIN)
        data = docx_bytes(paragraph("The body says nothing else."), {"word/footnotes.xml": footnotes})
        found, chunks = account_of("f.docx", data)
        shown = " ".join(chunk["text"] for chunk in chunks)
        if "spifflicated" not in shown:
            self.assertGreater(found["unaccounted"], 0, "a footnote vanished without the account saying so")
            self.assertTrue(any("spifflicated" in piece for piece in found["what unaccounted"]),
                            found["what unaccounted"])

    def test_a_word_only_in_a_docx_text_box_is_never_absent_without_a_word(self):
        box = ('<w:p><w:r><mc:AlternateContent xmlns:mc="x"><w:txbxContent><w:p><w:r>'
               '<w:t>The box says quinquagenarian.</w:t></w:r></w:p></w:txbxContent>'
               '</mc:AlternateContent></w:r></w:p>')
        found, chunks = account_of("b.docx", docx_bytes(paragraph("Body.") + box))
        shown = " ".join(chunk["text"] for chunk in chunks)
        if "quinquagenarian" not in shown:
            self.assertTrue(any("quinquagenarian" in piece for piece in found["what unaccounted"]),
                            "a text box vanished without the account saying so")

    def test_the_account_says_where_what_it_could_not_place_was_found(self):
        footnotes = ('<?xml version="1.0"?><w:footnotes xmlns:w="%s"><w:footnote w:id="1"><w:p><w:r>'
                     '<w:t>Antidisestablishmentarianism.</w:t></w:r></w:p></w:footnote></w:footnotes>' % WORD_MAIN)
        found, _ = account_of("w.docx", docx_bytes(paragraph("Body."), {"word/footnotes.xml": footnotes}))
        if found["unaccounted"]:
            self.assertTrue(found["where unaccounted"], "something was lost and the account cannot say where")
            self.assertTrue(any("footnotes" in where for where in found["where unaccounted"]))


class NothingIsAdded(unittest.TestCase):
    """Every word a unit shows comes from the file or from a transform named in the code."""

    def test_a_word_no_atom_holds_and_no_rule_explains_is_reported_as_added(self):
        atoms = [reading.atom("body", "f line 1", "The buffer is three per cent.")]
        chunks = [{"kind": "Paragraph", "text": "The buffer is four per cent.", "heading_chain": ()}]
        found = reading.account("f", atoms, chunks)
        self.assertEqual(found["injected"], 1)
        self.assertEqual(found["what injected"], ["four"])
        self.assertFalse(found["closed"])

    def test_the_samples_add_nothing_at_all(self):
        for sample in ("A_minimal", "D_dosing", "F_capital"):
            for found in helpers.accounts_of_sample(sample):
                self.assertEqual(found["injected"], 0,
                                 "%s %s shows words the file does not hold: %s"
                                 % (sample, found["file"], found["what injected"]))


class TheAccountClosesBecauseTheTransformsAreNamed(unittest.TestCase):
    """The point of naming a transform is that the account would not close without it. These
    prove the naming is load-bearing rather than decorative."""

    def test_a_heading_is_carried_not_copied(self):
        found, chunks = account_of("h.xml", "<doc><section><title>Capital</title>"
                                            "<para>One.</para><para>Two.</para></section></doc>")
        chains = [chunk["heading_chain"] for chunk in chunks]
        self.assertTrue(all("Capital" in chain for chain in chains), "the heading should reach every unit below it")
        self.assertEqual(found["injected"], 0, "a heading carried onto two units must not count as two additions")
        self.assertEqual(found["unaccounted"], 0)

    def test_without_the_marks_the_rendered_form_of_a_table_is_reported_as_added(self):
        atoms = [reading.atom("body", "t line 1", "Segment"), reading.atom("body", "t line 2", "Retail")]
        chunks = [{"kind": "Table", "text": "Segment;\nRetail;", "heading_chain": (),
                   "table": {"header": ["Segment"], "rows": [["Retail"]]}}]
        without = reading.account("t", atoms, chunks)
        with_marks = reading.account("t", atoms, chunks, marks=reading.marks_of_rendering(chunks))
        self.assertGreater(without["injected"], 0, "the rendered form should need a rule to explain it")
        self.assertEqual(with_marks["injected"], 0, "naming the rendering should explain it")

    def test_an_equation_is_neither_lost_nor_carried_but_rewritten(self):
        atoms = [reading.atom("equation", "e element 4 <math>", "D W R")]
        chunks = [{"kind": "Equation", "text": "d = w * r", "heading_chain": (),
                   "equation": {"source_form": "mathml", "linear": "d = w * r"}}]
        found = reading.account("e", atoms, chunks, marks=reading.marks_of_rendering(chunks))
        self.assertEqual(found["rewritten"], 3, "the symbols of an equation are read into another form")
        self.assertEqual(found["unaccounted"], 0, "and so are not a loss")
        self.assertIn("rewritten", reading.ATOM_CLASSES)

    def test_page_furniture_is_a_declared_drop_that_the_account_counts(self):
        atoms = [reading.atom("body", "p.1", "Running title"), reading.atom("body", "p.1", "Real text.")]
        chunks = [{"kind": "Paragraph", "text": "Real text.", "heading_chain": ()}]
        found = reading.account("p", atoms, chunks, dropped=["Running title"])
        self.assertEqual(found["declared drop"], 2)
        self.assertEqual(found["unaccounted"], 0)
        self.assertTrue(found["closed"])


class WhatTheAnalystIsTold(unittest.TestCase):
    def test_a_closed_account_says_so_in_plain_words(self):
        atoms = [reading.atom("body", "f line 1", "One two.")]
        found = reading.account("f", atoms, [{"kind": "Paragraph", "text": "One two.", "heading_chain": ()}])
        lines = reading.account_lines(found)
        self.assertTrue(any("nothing was lost and nothing was added" in line for line in lines))
        for line in lines:
            self.assertEqual(helpers.banned_wording(line), "", line)

    def test_an_open_account_says_how_much_and_where(self):
        atoms = [reading.atom("body", "f line 9", "A sentence nobody kept.")]
        found = reading.account("f", atoms, [{"kind": "Paragraph", "text": "", "heading_chain": ()}])
        lines = " ".join(reading.account_lines(found))
        self.assertIn("f line 9", lines)
        self.assertIn("in no unit and under no rule", lines)


class TheRunIsNeverStopped(unittest.TestCase):
    """R2 and R3: an open account is something a person is told about, never a halt."""

    def test_an_open_account_leaves_every_unit_in_place(self):
        found, chunks = account_of("s.html", "<html><head><style>p{margin:0}</style><title>Kept</title></head>"
                                             "<body><p>The body text.</p></body></html>")
        self.assertTrue(chunks, "the units must still be there")
        self.assertIn("The body text.", [chunk["text"] for chunk in chunks])


if __name__ == "__main__":
    unittest.main()
