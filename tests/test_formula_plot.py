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

    def test_rejects_names_attributes_keywords_and_code_execution(self):
        for expression in (
                "unknown(x)", "x.real", "__import__('os')",
                "max(x=1, 2)", "[x for x in (1, 2)]", "x**x",
                "x**101", "10000000000000"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    Formula(expression)

    def test_reports_domain_and_nonfinite_results(self):
        with self.assertRaises((ValueError, ZeroDivisionError)):
            Formula("1/x").evaluate(0)
        with self.assertRaises(ValueError):
            Formula("1e308 * 1e308").evaluate(0)


if __name__ == "__main__":
    unittest.main()
