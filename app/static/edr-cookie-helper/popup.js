// EDR Cookie Helper - Captures Walmart cookies and sends to Event Manager server
const statusEl = document.getElementById('status');
const sendBtn = document.getElementById('sendBtn');
const serverUrlInput = document.getElementById('serverUrl');
const cookieCountEl = document.getElementById('cookieCount');

// Load saved server URL
chrome.storage?.local?.get('serverUrl', (data) => {
  if (data.serverUrl) serverUrlInput.value = data.serverUrl;
});

// Show cookie count on popup open
countCookies();

async function countCookies() {
  try {
    const cookies = await chrome.cookies.getAll({ domain: '.wal-mart.com' });
    const cookies2 = await chrome.cookies.getAll({ domain: '.walmart.com' });
    const total = cookies.length + cookies2.length;
    cookieCountEl.textContent = total > 0
      ? `${total} Walmart cookies found`
      : 'No Walmart cookies found — log in first';
  } catch (e) {
    cookieCountEl.textContent = 'Could not read cookies';
  }
}

sendBtn.addEventListener('click', async () => {
  sendBtn.disabled = true;
  setStatus('info', 'Reading cookies...');

  try {
    // Get all cookies for Walmart domains (includes httpOnly)
    const cookies1 = await chrome.cookies.getAll({ domain: '.wal-mart.com' });
    const cookies2 = await chrome.cookies.getAll({ domain: 'wal-mart.com' });
    const cookies3 = await chrome.cookies.getAll({ domain: '.walmart.com' });
    const cookies4 = await chrome.cookies.getAll({ domain: 'walmart.com' });
    // Also get login subdomain cookies
    const cookies5 = await chrome.cookies.getAll({ domain: 'retaillink.login.wal-mart.com' });
    const cookies6 = await chrome.cookies.getAll({ domain: 'retaillink2.wal-mart.com' });

    // Deduplicate by name+domain+path
    const seen = new Set();
    const allCookies = [];
    for (const c of [...cookies1, ...cookies2, ...cookies3, ...cookies4, ...cookies5, ...cookies6]) {
      const key = `${c.name}|${c.domain}|${c.path}`;
      if (!seen.has(key)) {
        seen.add(key);
        allCookies.push({
          name: c.name,
          value: c.value,
          domain: c.domain,
          path: c.path,
          secure: c.secure,
          httpOnly: c.httpOnly,
          sameSite: c.sameSite,
          expirationDate: c.expirationDate,
        });
      }
    }

    if (allCookies.length === 0) {
      setStatus('warn', 'No Walmart cookies found. Please log into Retail Link first, then try again.');
      sendBtn.disabled = false;
      return;
    }

    setStatus('info', `Sending ${allCookies.length} cookies to server...`);

    // Save server URL
    const serverUrl = serverUrlInput.value.replace(/\/+$/, '');
    chrome.storage?.local?.set({ serverUrl });

    // Send to server
    const resp = await fetch(`${serverUrl}/printing/edr/import-cookies`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ cookies: allCookies }),
    });

    const data = await resp.json();

    if (data.success) {
      setStatus('success', data.message || 'Cookies imported! You can now generate paperwork.');
    } else {
      setStatus('error', data.error || 'Server rejected the cookies.');
      sendBtn.disabled = false;
    }
  } catch (err) {
    if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
      setStatus('error', `Cannot reach server. Check the URL and make sure you are logged into the Event Manager.`);
    } else {
      setStatus('error', `Failed to send: ${err.message}`);
    }
    sendBtn.disabled = false;
  }
});

function setStatus(type, msg) {
  statusEl.className = `status ${type}`;
  statusEl.textContent = msg;
}
