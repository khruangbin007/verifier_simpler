"""Tests of aiva1_documents: reading methodology and documentation files of every supported form."""
import unittest

import helpers
import aiva0_shared as shared
import aiva1_documents as documents
import build_samples

UNFAMILIAR_SCHEMA = """<section name=""b) Industry Risk"">
<paranum num=""36."" style=""Pleading Paragraph"">
The moderate weight assigned to industry risk is because such enterprises have higher barriers to entry.</paranum>
<paranum num=""37."">
Industry risk is assessed by applying &#34;<marked_data hyperlink=""yes"" rev_id=""18"" type=""article"">Methodology: Industry Risk</marked_data>.&#34; See Appendix III.</paranum>
<paranum num=""38."" style=""Pleading Paragraph"">
This paragraph has been deleted.</paranum>
<paranum num=""42."" style=""Pleading Paragraph"">
The blended industry risk score is a weighted average of those industry scores.</paranum>
</section>
<section name=""c) Market Position (60% weighting) "">
<paranum num=""43."" style=""Pleading Paragraph"">
Our market position assessment focuses on the role a provider plays within its industry.</paranum>
<table>
<tablerow>
<tablenumber width=""208"">
Table 2</tablenumber>
<tablecell width=""204""> </tablecell>
<tablecell width=""204""> </tablecell>
</tablerow>
<tablerow>
<tabletitle>
Market Position Assessment By Asset Class</tabletitle>
<tablecell> </tablecell>
<tablecell> </tablecell>
</tablerow>
<tablerow>
<tablecell>Asset class</tablecell>
<tablecell>Extremely strong</tablecell>
<tablecell>Vulnerable</tablecell>
</tablerow>
<tablerow>
<tablecell>Toll roads</tablecell>
<tablecell>Dominant position</tablecell>
<tablecell>Weak position</tablecell>
</tablerow>
</table>
</section>
"""


NOTATION = documents.load_notation(helpers.os.path.join(helpers.ENGINE_DIR, "references"))


class FormulaNotation(unittest.TestCase):
    def test_precedence_and_associativity(self):
        for text, expected in (("y = a - b - c", "y = a - b - c"), ("y = a/b/c", "y = a / b / c"), ("y = -x^2", "y = -x^2"),
                               ("y = 2^3^2", "y = 2^3^2"), ("y = a*(b + c)", "y = a * (b + c)"), ("y = 12.5% * x", "y = 0.125 * x")):
            self.assertEqual(shared.expr_to_text(documents.parse_formula(text, NOTATION)), expected)
        tree = documents.parse_formula("y = a - (b - c)", NOTATION)
        self.assertEqual(shared.expr_to_text(tree), "y = a - (b - c)")

    def test_functions_and_inverse(self):
        tree = documents.parse_formula("K = LGD * N((N^-1(PD) + sqrt(R) * N^-1(0.999)) / sqrt(1 - R))", NOTATION)
        names = [node.name for node in shared.expr_walk(tree) if node.op == "call"]
        self.assertEqual(sorted(set(names)), ["normal_cdf", "normal_inverse", "sqrt"])

    def test_ambiguous_notation_is_not_guessed(self):
        for text in ("y = 2x", "y = (a+b)(c+d)", "y = f(x)", "y = a +"):
            with self.assertRaises(documents.NotReadable, msg=text):
                documents.parse_formula(text, NOTATION)

    def test_juxtaposition_is_a_product_only_for_markup_sources(self):
        tree = documents.parse_formula("y = 2 x", NOTATION, implicit_product=True)
        self.assertEqual(shared.expr_to_text(tree), "y = 2 * x")

    def test_mathml_and_latex_conversion(self):
        import xml.etree.ElementTree as ET
        math = ET.fromstring('<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>y</mi><mo>=</mo><mfrac><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow>'
                             '<msqrt><mi>c</mi></msqrt></mfrac></math>')
        linear = documents.math_to_linear(math)
        self.assertEqual(shared.expr_to_text(documents.parse_formula(linear, NOTATION, implicit_product=True)), "y = (a + b) / sqrt(c)")
        latex = documents.latex_to_linear(r"K = \frac{a + b}{\sqrt{1 - \rho}} \cdot \Phi^{-1}(0.999)")
        tree = documents.parse_formula(latex, NOTATION, implicit_product=True)
        self.assertIn("normal_inverse", [n.name for n in shared.expr_walk(tree)])
        self.assertIn("rho", shared.expr_symbols(tree))


class UnfamiliarSchema(unittest.TestCase):
    """A schema nobody listed in tag_rules.yaml, read by the shape of its own markup."""

    def chunks(self):
        return helpers.chunks_of("method.txt", UNFAMILIAR_SCHEMA)

    def test_a_table_is_read_without_its_tags_being_listed_anywhere(self):
        chunks, _ = self.chunks()
        tables = [c for c in chunks if c["kind"] == "Table"]
        self.assertEqual(len(tables), 1, "the table is one chunk")
        table = tables[0]["table"]
        self.assertEqual(list(table["header"]), ["Asset class", "Extremely strong", "Vulnerable"])
        self.assertEqual([list(r) for r in table["rows"]], [["Toll roads", "Dominant position", "Weak position"]])
        self.assertIn("Table 2", tables[0]["caption"])
        self.assertIn("Market Position Assessment By Asset Class", tables[0]["caption"])

    def test_the_number_the_document_gives_a_paragraph_is_the_number_shown(self):
        chunks, _ = self.chunks()
        labels = [c["para_label"] for c in chunks if c["kind"] == "Paragraph"]
        self.assertEqual(labels, ["36.", "37.", "38.", "42.", "43."])

    def test_a_heading_carried_in_an_attribute_is_not_lost(self):
        chunks, _ = self.chunks()
        chains = {c["heading_chain"][-1] for c in chunks if c["heading_chain"]}
        self.assertIn("b) Industry Risk", chains)
        self.assertIn("c) Market Position (60% weighting)", chains)

    def test_a_tag_inside_running_text_stays_in_its_sentence(self):
        chunks, _ = self.chunks()
        paragraph = next(c for c in chunks if c["para_label"] == "37.")
        self.assertIn("Methodology: Industry Risk", paragraph["text"])
        self.assertEqual(sum(1 for c in chunks if "Methodology: Industry Risk" in c["text"]), 1)

    def test_every_inferred_tag_is_reported_with_its_reason(self):
        _, result = self.chunks()
        said = " ".join(row["value"] for row in result.records["info_rows"] if "unrecognised" in row["item"])
        for tag in ("paranum", "tablerow", "tablecell", "tabletitle"):
            self.assertIn("'%s'" % tag, said)
        self.assertIn("because it", said, "each one says why it was read that way")

    def test_the_skeleton_of_a_document_is_never_mistaken_for_a_table(self):
        """<methodology> holding <part>s holding <section>s repeats twice over exactly as a
        table does. What separates them is that a cell holds words and a section holds blocks."""
        chunks, _ = helpers.chunks_of("method.txt", build_samples.F_METHODOLOGY)
        self.assertEqual(sum(1 for c in chunks if c["kind"] == "Table"), 2)
        self.assertGreater(sum(1 for c in chunks if c["kind"] == "Paragraph"), 10)


class ReadingFiles(unittest.TestCase):
    def test_format_is_found_from_content_not_from_the_extension(self):
        self.assertEqual(documents.detect_format(b"%PDF-1.4 ..."), "pdf")
        self.assertEqual(documents.detect_format(b"<?xml version='1.0'?><a/>"), "xml")
        self.assertEqual(documents.detect_format(b"MIME-Version: 1.0\nContent-Type: multipart/related"), "mhtml")
        self.assertEqual(documents.detect_format(b"  <html><body>x</body></html>"), "html")
        self.assertEqual(documents.detect_format(b"Just some words."), "text")

    def test_xml_in_a_txt_file_nested_levels_tables_equations(self):
        chunks, result = helpers.chunks_of("method.txt", build_samples.F_METHODOLOGY)
        kinds = [c["kind"] for c in chunks]
        self.assertEqual((kinds.count("Table"), kinds.count("Equation")), (2, 2))
        self.assertEqual(max(c["level"] for c in chunks), 5)
        floor = next(c for c in chunks if "never taken below" in c["text"])
        self.assertEqual(floor["heading_chain"][-1], "3.1.1 Floor")
        readable = [c["equation"]["readable"] for c in chunks if c["kind"] == "Equation"]
        self.assertEqual(readable, [True, False])
        image = next(c for c in chunks if c["kind"] == "Equation" and not c["equation"]["readable"])
        self.assertEqual(image["equation"]["not_readable_reason"], "the equation is an image")
        annex = {c["numbering"]: c["level"] for c in chunks if c["heading_chain"] and c["heading_chain"][0].startswith("Annex") or c["numbering"] in ("I.", "(a)")}
        self.assertLess(annex["I."], annex["(a)"])

    def test_one_table_is_one_chunk_and_inline_formulas_are_found(self):
        chunks, _ = helpers.chunks_of("method.txt", build_samples.F_METHODOLOGY)
        table = next(c for c in chunks if c["kind"] == "Table" and "Retail" in c["text"])
        self.assertEqual(table["table"]["header"], ["Segment", "LGD floor"])
        self.assertEqual(len(table["table"]["rows"]), 3)
        inline = next(c for c in chunks if c["text"].startswith("The asset correlation falls"))
        self.assertTrue(inline["equation"]["readable"])
        self.assertEqual(inline["equation"]["source_form"], "inline")

    def test_malformed_markup_is_repaired_and_the_repairs_are_recorded(self):
        broken = "<doc><section><title>1 Scope</title><p>Costs & prices are set here.<p>A second one with a bad &entity; inside.</section></doc>"
        chunks, result = helpers.chunks_of("broken.xml", broken)
        self.assertEqual(len(chunks), 2)
        self.assertIn("Costs & prices", chunks[0]["text"])
        self.assertTrue(result.records["read_repairs"])

    def test_unknown_tags_are_read_and_reported(self):
        chunks, result = helpers.chunks_of("odd.xml", "<doc><sect><ttl>1 Scope</ttl><blurb>The rate is 5% for all.</blurb></sect></doc>")
        self.assertTrue(any("5%" in c["text"] for c in chunks))
        self.assertTrue(any("unrecognised tag" in row["item"].lower() for row in result.records["info_rows"]))

    def test_mhtml_keeps_preserved_equation_markup_and_skips_its_fallback_image(self):
        chunks, _ = helpers.chunks_of("method.mhtml", build_samples.mhtml_file(build_samples.D_HTML, ["image001.png", "image002.png"]))
        equations = [c for c in chunks if c["kind"] == "Equation"]
        self.assertEqual(len(equations), 1)
        self.assertEqual(equations[0]["text"], "D = W * R")
        self.assertEqual([c["kind"] for c in chunks].count("Figure"), 1)
        self.assertEqual(len(chunks), 9)

    def test_docx_headings_numbering_tables_equations_and_figures(self):
        chunks, _ = helpers.chunks_of("doc.docx", build_samples.docx_file(build_samples.f_documentation(False)), corner="documentation")
        kinds = [c["kind"] for c in chunks]
        self.assertEqual((kinds.count("Table"), kinds.count("Equation"), kinds.count("Figure")), (1, 1, 1))
        equation = next(c for c in chunks if c["kind"] == "Equation")
        self.assertTrue(equation["equation"]["readable"])
        self.assertIn("normal_inverse", equation["text"])
        self.assertEqual(next(c for c in chunks if "floor_pd" in c["text"])["heading_chain"], ["2 Risk components", "2.1 Probability of default"])

    def test_pdf_text_and_tables(self):
        chunks, _ = helpers.chunks_of("guide.pdf", build_samples.pdf_file(build_samples.F_USER_GUIDE), corner="documentation")
        self.assertTrue(any(c["kind"] == "Table" and "Retail" in c["text"] for c in chunks))
        self.assertTrue(any("scales the requirement by 12.5" in c["text"] for c in chunks))

    def test_a_file_that_cannot_be_read_gives_a_not_read_unit_and_never_stops_the_run(self):
        chunks, _ = helpers.chunks_of("broken.docx", b"PK\x03\x04 this is not a real archive", corner="documentation")
        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0]["not_read_reason"])

    def test_entities_defined_inside_an_office_file_are_never_expanded(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]><d>&b;</d>'
        with self.assertRaises(Exception):
            documents.safe_xml(bomb)
        self.assertEqual(documents.safe_xml(b'<?xml version="1.0"?><!DOCTYPE d><d>fine</d>').text, "fine")

    def test_checkable_statements_and_cross_references(self):
        chunks, _ = helpers.chunks_of("m.xml", "<doc><section><title>1 Rates</title><p>This part gives the background of the method.</p>"
                                               "<p>The rate is at least 3% as set out in Table 2 and section 4.1.</p></section></doc>", corner="documentation")
        self.assertEqual([c["checkable"] for c in chunks], [False, True])
        self.assertEqual(sorted(chunks[1]["refs_out"]), ["Table 2", "section 4.1"])

    def test_same_bytes_give_the_same_chunks(self):
        first, _ = helpers.chunks_of("method.txt", build_samples.F_METHODOLOGY)
        second, _ = helpers.chunks_of("method.txt", build_samples.F_METHODOLOGY)
        self.assertEqual([c["content_hash"] for c in first], [c["content_hash"] for c in second])
        self.assertEqual([c["ref"] for c in first], ["C-%04d" % n for n in range(1, len(first) + 1)])


if __name__ == "__main__":
    unittest.main()
