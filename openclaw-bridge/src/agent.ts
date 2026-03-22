/**
 * AgentServer — HTTP server that speaks the OpenClaw agent protocol.
 *
 * The @tencent-weixin/openclaw-weixin-cli plugin discovers agents by scanning
 * localhost for the /.well-known/openclaw manifest, then POSTs inbound WeChat
 * messages to the endpoint declared in that manifest.
 *
 * This server is the protocol boundary: it translates between the OpenClaw
 * plugin protocol and the simple JSON events used on the bridge/Python side.
 */

import http from 'http';

export interface WechatMessage {
  openid:   string;
  chat_id:  string;
  content:  string;
  msg_id:   string;
  nickname: string;
  is_group: boolean;
  timestamp: number;
}

export type MessageHandler = (msg: WechatMessage) => void;
export type SendFn = (openid: string, content: string) => Promise<void>;

export class AgentServer {
  private server: http.Server;
  private onMessage: MessageHandler | null = null;
  // Callback URL registered by the plugin on its first connection
  private pluginCallbackUrl: string | null = null;

  constructor(private port: number, private token?: string) {
    this.server = http.createServer((req, res) => this.handleRequest(req, res));
  }

  /** Register the handler that will receive inbound WeChat messages. */
  setMessageHandler(handler: MessageHandler): void {
    this.onMessage = handler;
  }

  start(): void {
    this.server.listen(this.port, '127.0.0.1', () => {
      console.log(`🔌 OpenClaw agent server listening on http://127.0.0.1:${this.port}`);
      console.log(`   Discovery: GET  http://127.0.0.1:${this.port}/.well-known/openclaw`);
      console.log(`   Messages:  POST http://127.0.0.1:${this.port}/message\n`);
    });
  }

  stop(): void {
    this.server.close();
  }

  /** Send a reply to the WeChat user via the plugin's callback URL. */
  async send(openid: string, content: string): Promise<void> {
    if (!this.pluginCallbackUrl) {
      console.warn('No plugin callback URL registered yet, cannot send reply');
      return;
    }
    const body = JSON.stringify({ to: openid, content });
    await fetch(this.pluginCallbackUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(this.token ? { 'X-Openclaw-Token': this.token } : {}) },
      body,
    }).catch((err) => console.error('Failed to send reply to plugin:', err));
  }

  private handleRequest(req: http.IncomingMessage, res: http.OutgoingMessage & { writeHead: Function; end: Function }): void {
    if (req.method === 'GET' && req.url === '/.well-known/openclaw') {
      this.handleDiscovery(res);
    } else if (req.method === 'GET' && req.url === '/.well-known/openclaw/health') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ ok: true }));
    } else if (req.method === 'POST' && req.url === '/message') {
      this.handleInbound(req, res);
    } else {
      res.writeHead(404);
      res.end();
    }
  }

  /** GET /.well-known/openclaw — plugin auto-discovery manifest. */
  private handleDiscovery(res: any): void {
    const manifest = {
      type: 'agent',
      vendor: 'comobot',
      openclaw_version: '1.0',
      capabilities: ['text', 'image', 'group'],
      // Plugin will POST inbound messages here
      message_endpoint: `http://127.0.0.1:${this.port}/message`,
      // Plugin sends its own callback URL as a registration field
      status: 'ready',
    };
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(manifest));
    console.log('📡 OpenClaw plugin discovered this bridge');
  }

  /** POST /message — plugin pushes inbound WeChat messages here. */
  private handleInbound(req: http.IncomingMessage, res: any): void {
    // Optional token check
    if (this.token) {
      const provided = req.headers['x-openclaw-token'];
      if (provided !== this.token) {
        res.writeHead(403, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Invalid token' }));
        return;
      }
    }

    let body = '';
    req.on('data', (chunk: Buffer) => { body += chunk.toString(); });
    req.on('end', () => {
      try {
        const data = JSON.parse(body);

        // If the plugin provides its callback URL, remember it
        if (data.callback_url) {
          this.pluginCallbackUrl = data.callback_url;
        }

        const msg: WechatMessage = {
          openid:    data.openid   || data.from || '',
          chat_id:   data.chat_id  || data.openid || data.from || '',
          content:   data.content  || data.text || '',
          msg_id:    data.msg_id   || data.id || '',
          nickname:  data.nickname || data.name || '',
          is_group:  Boolean(data.is_group || data.group),
          timestamp: data.timestamp || Math.floor(Date.now() / 1000),
        };

        if (this.onMessage && msg.openid && msg.content) {
          this.onMessage(msg);
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Invalid JSON' }));
      }
    });
  }
}
