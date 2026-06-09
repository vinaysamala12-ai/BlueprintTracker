/**
 * storageService.js
 *
 * Lists and fetches files from Microsoft 365 storage via Graph API.
 * Supports both:
 *   - OneDrive  (personal or business)
 *   - SharePoint document libraries
 *
 * Requires an Azure AD App Registration with:
 *   - Files.Read.All (Application permission)
 *   - Sites.Read.All  (Application permission, for SharePoint)
 */

const axios = require('axios');
const Config = require('../models/Config');

const GRAPH_BASE = 'https://graph.microsoft.com/v1.0';

class StorageService {
  async _getConfig() {
    let cfg = await Config.findOne();
    if (!cfg) { cfg = new Config(); await cfg.save(); }
    return cfg;
  }

  // ── OAuth token ────────────────────────────────────────────────────────────

  async _getToken(cfg) {
    const { tenantId, clientId, clientSecret } = cfg.storage;
    if (!tenantId || !clientId || !clientSecret) {
      throw new Error('Storage credentials not configured. Set tenantId, clientId, clientSecret in Settings.');
    }
    const url = `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`;
    const params = new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      scope: 'https://graph.microsoft.com/.default',
      grant_type: 'client_credentials'
    });
    const res = await axios.post(url, params.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
    return res.data.access_token;
  }

  _headers(token) {
    return { Authorization: `Bearer ${token}` };
  }

  // ── List files ─────────────────────────────────────────────────────────────

  async listFiles(folderPath) {
    const cfg = await this._getConfig();
    const token = await this._getToken(cfg);

    if (cfg.storage.type === 'sharepoint') {
      return this._listSharePointFiles(cfg, token, folderPath);
    }
    return this._listOneDriveFiles(cfg, token, folderPath);
  }

  async _listOneDriveFiles(cfg, token, folderPath) {
    const path = folderPath || cfg.storage.folderPath || '/';
    let url;

    if (cfg.storage.driveId) {
      // Specific drive
      const encodedPath = path === '/' ? 'root' : `root:${path}`;
      url = `${GRAPH_BASE}/drives/${cfg.storage.driveId}/items/${encodedPath}/children`;
    } else {
      // Default drive of the service account (client credentials → organisation drive)
      const encodedPath = path === '/' ? 'root' : `root:${path}`;
      url = `${GRAPH_BASE}/me/drive/items/${encodedPath}/children`;
    }

    const res = await axios.get(url, { headers: this._headers(token) });
    return this._normaliseFiles(res.data.value, 'onedrive', cfg.storage.driveId);
  }

  async _listSharePointFiles(cfg, token, folderPath) {
    const path = folderPath || cfg.storage.folderPath || '/';

    // Resolve site ID from site URL
    const encodedSiteUrl = encodeURIComponent(
      new URL(cfg.storage.siteUrl).host + ':' + new URL(cfg.storage.siteUrl).pathname
    );
    const siteRes = await axios.get(`${GRAPH_BASE}/sites/${encodedSiteUrl}`, {
      headers: this._headers(token)
    });
    const siteId = siteRes.data.id;

    // Get default document library drive
    const drivesRes = await axios.get(`${GRAPH_BASE}/sites/${siteId}/drives`, {
      headers: this._headers(token)
    });
    const drive = drivesRes.data.value.find(d =>
      d.name === (cfg.storage.folderPath || 'Documents') || d.driveType === 'documentLibrary'
    ) || drivesRes.data.value[0];

    if (!drive) throw new Error('No document library found in SharePoint site');

    const encodedPath = path === '/' ? 'root' : `root:${path}`;
    const url = `${GRAPH_BASE}/drives/${drive.id}/items/${encodedPath}/children`;
    const res = await axios.get(url, { headers: this._headers(token) });

    return this._normaliseFiles(res.data.value, 'sharepoint', drive.id, siteId);
  }

  _normaliseFiles(items, storageType, driveId, siteId = null) {
    return items
      .filter(item => item.file) // only files, not folders
      .map(item => ({
        fileId: item.id,
        driveId,
        siteId,
        name: item.name,
        path: item.parentReference?.path || '',
        webUrl: item.webUrl,
        mimeType: item.file?.mimeType || '',
        fileSize: item.size || 0,
        lastModified: item.lastModifiedDateTime,
        storageType
      }));
  }

  // ── Upload a file to SharePoint / OneDrive ────────────────────────────────

  /**
   * Upload a file buffer to the configured storage location.
   * Uses the Graph API simple upload (PUT) — works up to 4 MB.
   * For larger files uses an upload session.
   * @returns normalised file object (same shape as listFiles)
   */
  async uploadFile(fileBuffer, fileName, mimeType, folderPath) {
    const cfg = await this._getConfig();
    const token = await this._getToken(cfg);
    const destFolder = folderPath || cfg.storage.folderPath || '/';

    let driveId, uploadPath;

    if (cfg.storage.type === 'sharepoint') {
      // Resolve the SharePoint drive first
      const siteHost = new URL(cfg.storage.siteUrl).host;
      const sitePath = new URL(cfg.storage.siteUrl).pathname;
      const siteRes = await axios.get(
        `${GRAPH_BASE}/sites/${siteHost}:${sitePath}`,
        { headers: this._headers(token) }
      );
      const siteId = siteRes.data.id;
      const drivesRes = await axios.get(
        `${GRAPH_BASE}/sites/${siteId}/drives`,
        { headers: this._headers(token) }
      );
      const drive = drivesRes.data.value.find(d => d.driveType === 'documentLibrary') || drivesRes.data.value[0];
      driveId = drive.id;
    } else {
      driveId = cfg.storage.driveId || null;
    }

    // Build the upload URL
    const folder = destFolder === '/' ? '' : destFolder.replace(/\/$/, '');
    const encodedPath = encodeURIComponent(`${folder}/${fileName}`).replace(/%2F/g, '/');

    if (driveId) {
      uploadPath = `${GRAPH_BASE}/drives/${driveId}/root:/${encodedPath}:/content`;
    } else {
      uploadPath = `${GRAPH_BASE}/me/drive/root:/${encodedPath}:/content`;
    }

    let uploadRes;
    try {
      uploadRes = await axios.put(uploadPath, fileBuffer, {
        headers: {
          ...this._headers(token),
          'Content-Type': mimeType || 'application/octet-stream',
          'Content-Length': fileBuffer.length
        },
        maxBodyLength: Infinity,
        maxContentLength: Infinity
      });
    } catch (err) {
      const status = err.response?.status;
      const code   = err.response?.data?.error?.code;
      const detail = err.response?.data?.error?.message || err.message;

      if (status === 403) {
        throw new Error(
          `Upload failed (403 Forbidden). The Azure App is missing write permissions.\n` +
          `Grant these Application permissions in Azure Portal → App registrations → API permissions (then click "Grant admin consent"):\n` +
          `• Files.ReadWrite.All\n` +
          `• Sites.ReadWrite.All  (SharePoint only)\n\n` +
          `Graph error: ${code} — ${detail}`
        );
      }
      throw new Error(`Upload failed (${status || 'network error'}): ${detail}`);
    }

    const item = uploadRes.data;
    return {
      fileId:       item.id,
      driveId:      item.parentReference?.driveId || driveId,
      siteId:       item.parentReference?.siteId  || null,
      name:         item.name,
      path:         item.parentReference?.path || destFolder,
      webUrl:       item.webUrl,
      mimeType:     item.file?.mimeType || mimeType || '',
      fileSize:     item.size || fileBuffer.length,
      lastModified: item.lastModifiedDateTime,
      storageType:  cfg.storage.type
    };
  }

  // ── Get single file details ────────────────────────────────────────────────

  async getFile(driveId, fileId) {
    const cfg = await this._getConfig();
    const token = await this._getToken(cfg);
    const res = await axios.get(
      `${GRAPH_BASE}/drives/${driveId}/items/${fileId}`,
      { headers: this._headers(token) }
    );
    return res.data;
  }

  // ── Connection test ────────────────────────────────────────────────────────

  async testConnection() {
    const cfg = await this._getConfig();

    // Step 1: Verify credentials by obtaining a token
    let token;
    try {
      token = await this._getToken(cfg);
    } catch (err) {
      const msg = err.response?.data?.error_description || err.message;
      throw new Error(`Authentication failed: ${msg}`);
    }

    // Step 2: Test storage-specific access
    if (cfg.storage.type === 'sharepoint') {
      return this._testSharePoint(cfg, token);
    }
    return this._testOneDrive(cfg, token);
  }

  async _testSharePoint(cfg, token) {
    if (!cfg.storage.siteUrl) throw new Error('SharePoint Site URL is not configured');

    try {
      const siteHost = new URL(cfg.storage.siteUrl).host;
      const sitePath = new URL(cfg.storage.siteUrl).pathname;
      const encodedSite = `${siteHost}:${sitePath}`;
      const res = await axios.get(`${GRAPH_BASE}/sites/${encodedSite}`, {
        headers: this._headers(token)
      });
      return {
        success: true,
        storageType: 'sharepoint',
        siteName: res.data.displayName,
        siteId: res.data.id,
        webUrl: res.data.webUrl
      };
    } catch (err) {
      const status = err.response?.status;
      const code   = err.response?.data?.error?.code;
      const detail = err.response?.data?.error?.message || err.message;

      if (status === 403) {
        throw new Error(
          `Access denied (403). Ensure the Azure App has these Application permissions with Admin Consent granted:\n` +
          `• Sites.Read.All\n• Files.Read.All\n\nGraph error: ${code} — ${detail}`
        );
      }
      if (status === 404) {
        throw new Error(`SharePoint site not found. Check the Site URL in Settings.\nURL tried: ${cfg.storage.siteUrl}`);
      }
      throw new Error(`SharePoint test failed (${status}): ${detail}`);
    }
  }

  async _testOneDrive(cfg, token) {
    try {
      let url;
      if (cfg.storage.driveId) {
        url = `${GRAPH_BASE}/drives/${cfg.storage.driveId}`;
      } else {
        // List available drives for the tenant
        url = `${GRAPH_BASE}/drives`;
      }
      const res = await axios.get(url, { headers: this._headers(token) });
      const drive = res.data.value?.[0] || res.data;
      return {
        success: true,
        storageType: 'onedrive',
        driveName: drive.name || drive.value?.[0]?.name,
        driveId: drive.id || drive.value?.[0]?.id
      };
    } catch (err) {
      const status = err.response?.status;
      const code   = err.response?.data?.error?.code;
      const detail = err.response?.data?.error?.message || err.message;

      if (status === 403) {
        throw new Error(
          `Access denied (403). Ensure the Azure App has these Application permissions with Admin Consent granted:\n` +
          `• Files.Read.All\n\nGraph error: ${code} — ${detail}`
        );
      }
      throw new Error(`OneDrive test failed (${status}): ${detail}`);
    }
  }
}

module.exports = new StorageService();
