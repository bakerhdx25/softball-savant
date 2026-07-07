const COOKIE_NAME = "softball_savant_access";

function loginPage(error = "") {
  return new Response(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  <title>Softball Savant</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f4f5f6; color: #17191c; font-family: Inter, Arial, sans-serif; }
    form { width: min(100% - 32px, 420px); border: 1px solid #d8dde2; background: white; padding: 28px; }
    h1 { margin: 0 0 10px; font-size: 32px; letter-spacing: -.04em; }
    p { margin: 0 0 20px; color: #6c7580; }
    label { display: grid; gap: 8px; color: #6c7580; font-size: 11px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
    input { min-height: 46px; border: 1px solid #aeb7c2; padding: 0 12px; font: inherit; }
    button { width: 100%; min-height: 48px; margin-top: 14px; border: 0; background: #17191c; color: white; font-weight: 900; }
    .error { margin-top: 12px; color: #b42318; font-weight: 800; }
  </style>
</head>
<body>
  <form method="post">
    <h1>Softball Savant</h1>
    <p>Enter the access password to view the site.</p>
    <label>Password<input name="password" type="password" autocomplete="current-password" autofocus></label>
    <button type="submit">Open site</button>
    ${error ? `<div class="error">${error}</div>` : ""}
  </form>
</body>
</html>`, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

async function accessToken(password) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(password));
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}

async function hasAccess(request, password) {
  const cookie = request.headers.get("cookie") || "";
  const token = await accessToken(password);
  return cookie.split(";").some(part => part.trim() === `${COOKIE_NAME}=${token}`);
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const password = env.SOFTBALL_SAVANT_PASSWORD;
  if (!password) return next();

  const url = new URL(request.url);
  if (url.pathname === "/robots.txt") return next();

  if (request.method === "POST") {
    const form = await request.formData();
    if (form.get("password") === password) {
      const token = await accessToken(password);
      return new Response(null, {
        status: 303,
        headers: {
          "location": url.pathname,
          "set-cookie": `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`,
          "cache-control": "no-store",
        },
      });
    }
    return loginPage("Wrong password.");
  }

  if (await hasAccess(request, password)) return next();
  return loginPage();
}
