#!/usr/bin/env node
/**
 * comobot OpenClaw WeChat Bridge
 *
 * Sits between the @tencent-weixin/openclaw-weixin-cli plugin and comobot's
 * Python backend.  Two independent servers run in a single process:
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  openclaw-bridge (this process)                              │
 *   │                                                              │
 *   │  AgentServer  (HTTP, PLUGIN_PORT=19088)                      │
 *   │    GET  /.well-known/openclaw  ← plugin auto-discovery       │
 *   │    POST /message               ← plugin sends WeChat msgs    │
 *   │    (sends replies via POST back to plugin's callback URL)    │
 *   │                                                              │
 *   │  BridgeServer (WebSocket, BRIDGE_PORT=3002)                  │
 *   │    ← Python WechatChannel connects here                      │
 *   │    forwards messages both ways                               │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Environment variables:
 *   BRIDGE_PORT   WebSocket port for Python side  (default: 3002)
 *   PLUGIN_PORT   HTTP port for OpenClaw plugin   (default: 19088)
 *   BRIDGE_TOKEN  Shared secret for Python auth   (optional)
 *   AUTH_DIR      Directory for session state     (default: ~/.comobot/wechat-auth)
 */

import { BridgeServer } from './server.js';
import { AgentServer } from './agent.js';
import { homedir } from 'os';
import { join } from 'path';

const BRIDGE_PORT = parseInt(process.env.BRIDGE_PORT || '3002', 10);
const PLUGIN_PORT = parseInt(process.env.PLUGIN_PORT || '19088', 10);
const TOKEN       = process.env.BRIDGE_TOKEN || undefined;
const AUTH_DIR    = process.env.AUTH_DIR || join(homedir(), '.comobot', 'wechat-auth');

console.log('🤖 comobot OpenClaw WeChat Bridge');
console.log('==================================\n');

// Agent HTTP server — speaks OpenClaw protocol to the plugin
const agent = new AgentServer(PLUGIN_PORT, TOKEN);

// WebSocket bridge server — speaks simple JSON protocol to Python
const bridge = new BridgeServer(BRIDGE_PORT, TOKEN, agent);

process.on('SIGINT', async () => {
  console.log('\n\nShutting down...');
  await bridge.stop();
  agent.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await bridge.stop();
  agent.stop();
  process.exit(0);
});

agent.start();
await bridge.start();
