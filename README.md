# Redirect Ghost

**Redirect Ghost** is a tiny, dependency-free CLI that simulates redirects from multiple web-server layers **before you deploy them**.

It can read a practical subset of:

- Apache `.htaccess`
- Nginx `rewrite` / `return`
- Cloudflare Pages `_redirects`

Then it walks a URL through the rules, prints the redirect chain, and warns about loops.

> Why? Redirect bugs are annoying because the rule can be valid by itself but become wrong after another layer touches the same URL.

## Example

```bash
python redirect_ghost.py \
  https://example.com/old-page \
  --apache examples/apache.htaccess \
  --nginx examples/nginx.conf \
  --cloudflare examples/_redirects
```

Example output:

```text
START  https://example.com/old-page
301    apache      https://example.com/archive
302    cloudflare  https://example.com/new-home
END    https://example.com/new-home
```

If the URL repeats, Redirect Ghost stops and reports a loop.

## Supported rule shapes

### Apache

```apache
Redirect 301 /old-page /archive
RewriteRule ^archive$ /new-home [R=302,L]
```

### Nginx

```nginx
rewrite ^/old/(.*)$ /new/$1 permanent;
return 302 https://example.com/maintenance;
```

### Cloudflare Pages

```text
/legacy /new-home 301
/blog/* /posts/:splat 302
```

This is intentionally a small parser, not a full Apache/Nginx emulator. The goal is to catch common redirect mistakes quickly.

## Usage

```bash
python redirect_ghost.py URL [options]

Options:
  --apache FILE
  --nginx FILE
  --cloudflare FILE
  --max-hops N
```

You can load one format or combine all three.

## Good first issues

- Support Apache `RewriteCond`
- Parse Nginx `location` blocks more precisely
- Add JSON output
- Add a Mermaid redirect graph
- Add GitHub Action mode

## License

MIT
