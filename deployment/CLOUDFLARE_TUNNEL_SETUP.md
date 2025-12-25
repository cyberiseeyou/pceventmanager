# Cloudflare Tunnel Setup (The "Router-Bypass" Method)

Since your server is on a residential network (Charter/Spectrum) or behind a router, port forwarding can be difficult or blocked. **Cloudflare Tunnel** creates a secure outbound connection so you don't need to open any ports.

## 1. Create a Tunnel in Cloudflare Dashboard

1. Go to [Cloudflare Zero Trust Dashboard](https://one.dash.cloudflare.com).
2. Navigate to **Networks** > **Tunnels**.
3. Click **Create a Tunnel**.
4. Choose **Cloudflared** connector.
5. Name it `server-tunnel` and save.
6. **Copy the installation command** for "Debian" / "Ubuntu" (it will look like `curl ... | sudo cloudflared service install <TOKEN>`).

## 2. Install on Server

Run the command you copied on your server:

```powershell
# From your local terminal
ssh elliot@ser6
# PASTE THE COMMAND HERE
```

## 3. Configure the Public Hostname

Back in the Cloudflare Dashboard (where you created the tunnel):

1. Click **Next** (Public Hostname).
2. **Subdomain**: `www` (or leave blank for root domain).
3. **Domain**: `cybermc.site`.
4. **Service**:
    * **Type**: `HTTP`
    * **URL**: `localhost:80`
5. Click **Save Tunnel**.

## 4. Final Cleanup

Since the Tunnel handles the connection, you don't strictly *need* Nginx's SSL anymore (Cloudflare handles SSL), but keeping the current Docker setup is fine. The Tunnel will talk to Nginx on port 80 locally.

**You should now be able to access <https://cybermc.site> immediately!**
