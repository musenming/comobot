/**
 * BridgeServer — WebSocket server for Python ↔ Node.js communication.
 *
 * Mirrors the WhatsApp bridge's server.ts exactly:
 *   - Binds to 127.0.0.1 only
 *   - Optional BRIDGE_TOKEN handshake authentication
 *   - Broadcasts inbound WeChat messages to all connected Python clients
 *   - Accepts {"type":"send","to":"<openid>","text":"..."} commands from Python
 */

import { WebSocketServer, WebSocket } from 'ws';
import { AgentServer, WechatMessage } from './agent.js';

interface SendCommand {
  type: 'send';
  to: string;
  text: string;
}

interface BridgeMessage {
  type: string;
  [key: string]: unknown;
}

export class BridgeServer {
  private wss: WebSocketServer | null = null;
  private clients: Set<WebSocket> = new Set();

  constructor(
    private port: number,
    private token: string | undefined,
    private agent: AgentServer,
  ) {
    // Wire agent inbound messages → Python clients
    this.agent.setMessageHandler((msg: WechatMessage) => {
      this.broadcast({
        type: 'message',
        openid:    msg.openid,
        chat_id:   msg.chat_id,
        content:   msg.content,
        msg_id:    msg.msg_id,
        nickname:  msg.nickname,
        is_group:  msg.is_group,
        timestamp: msg.timestamp,
      });
    });
  }

  async start(): Promise<void> {
    this.wss = new WebSocketServer({ host: '127.0.0.1', port: this.port });
    console.log(`🌉 Bridge WebSocket server listening on ws://127.0.0.1:${this.port}`);
    if (this.token) console.log('🔒 Bridge token authentication enabled');

    this.wss.on('connection', (ws) => {
      if (this.token) {
        const timeout = setTimeout(() => ws.close(4001, 'Auth timeout'), 5000);
        ws.once('message', (data) => {
          clearTimeout(timeout);
          try {
            const msg = JSON.parse(data.toString());
            if (msg.type === 'auth' && msg.token === this.token) {
              console.log('🔗 Python client authenticated');
              this.setupClient(ws);
            } else {
              ws.close(4003, 'Invalid token');
            }
          } catch {
            ws.close(4003, 'Invalid auth message');
          }
        });
      } else {
        console.log('🔗 Python client connected (no auth)');
        this.setupClient(ws);
      }
    });

    // Keep promise alive (server runs until stop())
    await new Promise<void>((resolve) => {
      this.wss!.on('close', resolve);
    });
  }

  private setupClient(ws: WebSocket): void {
    this.clients.add(ws);

    ws.on('message', async (data) => {
      try {
        const cmd = JSON.parse(data.toString()) as SendCommand;
        if (cmd.type === 'send') {
          await this.agent.send(cmd.to, cmd.text);
          ws.send(JSON.stringify({ type: 'sent', to: cmd.to }));
        }
      } catch (err) {
        console.error('Error handling send command:', err);
        ws.send(JSON.stringify({ type: 'error', error: String(err) }));
      }
    });

    ws.on('close', () => {
      console.log('🔌 Python client disconnected');
      this.clients.delete(ws);
    });

    ws.on('error', (err) => {
      console.error('WebSocket client error:', err);
      this.clients.delete(ws);
    });
  }

  private broadcast(msg: BridgeMessage): void {
    const data = JSON.stringify(msg);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  async stop(): Promise<void> {
    for (const client of this.clients) client.close();
    this.clients.clear();
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }
  }
}
