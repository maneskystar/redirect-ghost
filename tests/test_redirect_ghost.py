import tempfile
import unittest
from pathlib import Path

import redirect_ghost as rg


class RedirectGhostTests(unittest.TestCase):
    def test_cloudflare_wildcard(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "_redirects"
            p.write_text("/blog/* /posts/:splat 301\n", encoding="utf-8")
            rules = rg.cloudflare_rules(p)
            chain, final_url, loop = rg.simulate(
                "https://example.com/blog/hello", rules
            )
            self.assertFalse(loop)
            self.assertEqual(final_url, "https://example.com/posts/hello")
            self.assertEqual(chain[0][0], 301)

    def test_loop_detection(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "_redirects"
            p.write_text("/a /b 301\n/b /a 301\n", encoding="utf-8")
            rules = rg.cloudflare_rules(p)
            chain, final_url, loop = rg.simulate("https://example.com/a", rules)
            self.assertTrue(loop)
            self.assertEqual(final_url, "https://example.com/a")
            self.assertEqual(len(chain), 2)


if __name__ == "__main__":
    unittest.main()
