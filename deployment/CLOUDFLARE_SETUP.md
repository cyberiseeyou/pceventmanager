# Cloudflare & Domain Setup for cybermc.site

Since `cybermc.site` is already set up on Cloudflare, you just need to point it to your server.

## 1. Configure DNS in Cloudflare

1. Log in to your [Cloudflare Dashboard](https://dash.cloudflare.com).
2. Select **cybermc.site**.
3. Go to **DNS** > **Records**.
4. Add an **A Record**:
    * **Type**: A
    * **Name**: @ (root)
    * **IPv4 Address**: `[YOUR_SERVER_IP]` (Run `curl ifconfig.me` on your server to find this)
    * **Proxy Status**: Proxied (Orange Cloud) - **Recommended** for SSL and security.
5. Add a **CNAME Record** (for www):
    * **Type**: CNAME
    * **Name**: www
    * **Target**: cybermc.site
    * **Proxy Status**: Proxied.

## 2. SSL/TLS Settings

1. Go to **SSL/TLS** > **Overview**.
2. Set encryption mode to **Full**.
    * *Flexible*: Use if you haven't set up SSL on Nginx yet.
    * *Full*: Required if Nginx is configured with a self-signed cert or listening on 443.
    * *Full (Strict)*: Required if you use a valid Let's Encrypt cert on Nginx.

## 3. Deployment

Run the deployment script locally to push your code and database:

```powershell
.\deployment\deploy_remote.ps1
```
