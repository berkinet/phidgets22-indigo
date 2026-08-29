import pathlib
import sys
import unittest


SERVER_PLUGIN = pathlib.Path(__file__).parents[1] / "Phidgets22.indigoPlugin" / "Contents" / "Server Plugin"
sys.path.insert(0, str(SERVER_PLUGIN))

from formula_plot import Formula


class FormulaTests(unittest.TestCase):
    def test_math_expression_uses_x_constants_and_approved_functions(self):
        formula = Formula("sin(x) + cos(pi) + max(2, e)")
        self.assertAlmostEqual(formula.evaluate(0), -1 + 2.718281828459045)
        self.assertEqual(Formula("x**-2").evaluate(2), 0.25)

    def test_rejects_names_attributes_keywords_and_code_execution(self):
        for expression in (
                "unknown(x)", "x.real", "__import__('os')",
                "max(x=1, 2)", "[x for x in (1, 2)]", "x**x",
                "x**101", "x**-101", "10000000000000"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    Formula(expression)

    def test_reports_domain_and_nonfinite_results(self):
        with self.assertRaises((ValueError, ZeroDivisionError)):
            Formula("1/x").evaluate(0)
        with self.assertRaises(ValueError):
            Formula("1e308 * 1e308").evaluate(0)

    def test_boolean_comparison_and_conditional_expressions(self):
        self.assertEqual(Formula("True").evaluate(0), 1.0)
        self.assertEqual(Formula("x > 2.5").evaluate(2.5), 0.0)
        self.assertEqual(Formula("x > 2.5").evaluate(3), 1.0)
        self.assertEqual(Formula("10 <= x <= 20").evaluate(15), 1.0)
        self.assertEqual(
            Formula("1 if (x < 2.5 or x > 7.5) and not False else 0")
            .evaluate(8), 1.0)

    def test_round_and_clamp_are_bounded_helpers(self):
        self.assertEqual(Formula("round(x, 2)").evaluate(1.234), 1.23)
        self.assertEqual(Formula("clamp(x, 0, 100)").evaluate(120), 100.0)
        for expression in (
                "round(x, x)", "round(x, 16)", "round(x, 1.5)",
                "clamp(x, 0)"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    Formula(expression)
        with self.assertRaises(ValueError):
            Formula("clamp(x, 10, 0)").evaluate(5)


if __name__ == "__main__":
    unittest.main()
