/**
 * WebSocket streaming client with bounded exponential backoff reconnection.
 */

import type { WebSocketSnapshotMessage } from '../types';
import { API_BASE_URL } from './api';

export type ConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'error';

export interface WebSocketClientOptions {
  onMessage?: (snapshot: WebSocketSnapshotMessage) => void;
  onStatusChange?: (status: ConnectionStatus, detail?: string) => void;
  maxReconnectAttempts?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
}

export class RunWebSocketClient {
  private runId: string | null = null;
  private ws: WebSocket | null = null;
  private status: ConnectionStatus = 'idle';
  private reconnectAttempts = 0;
  private reconnectTimer: any = null;
  private isIntentionallyClosed = false;

  private onMessageCallback?: (snapshot: WebSocketSnapshotMessage) => void;
  private onStatusChangeCallback?: (status: ConnectionStatus, detail?: string) => void;
  private maxReconnectAttempts: number;
  private initialBackoffMs: number;
  private maxBackoffMs: number;

  constructor(options: WebSocketClientOptions = {}) {
    this.onMessageCallback = options.onMessage;
    this.onStatusChangeCallback = options.onStatusChange;
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 10;
    this.initialBackoffMs = options.initialBackoffMs ?? 1000;
    this.maxBackoffMs = options.maxBackoffMs ?? 5000;
  }

  public connect(runId: string): void {
    if (this.runId === runId && (this.status === 'connected' || this.status === 'connecting')) {
      return;
    }

    this.disconnect();
    this.runId = runId;
    this.isIntentionallyClosed = false;
    this.reconnectAttempts = 0;
    this._initiateConnection();
  }

  public disconnect(): void {
    this.isIntentionallyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }
    this._setStatus('disconnected', 'Disconnected by client');
  }

  public setOnMessage(callback: (snapshot: WebSocketSnapshotMessage) => void): void {
    this.onMessageCallback = callback;
  }

  public setOnStatusChange(callback: (status: ConnectionStatus, detail?: string) => void): void {
    this.onStatusChangeCallback = callback;
  }

  private _getWsUrl(runId: string): string {
    const wsBase = API_BASE_URL.replace(/^http:\/\//, 'ws://').replace(/^https:\/\//, 'wss://');
    return `${wsBase}/api/runs/${encodeURIComponent(runId)}/live`;
  }

  private _initiateConnection(): void {
    if (!this.runId || this.isIntentionallyClosed) return;

    const url = this._getWsUrl(this.runId);
    this._setStatus(this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting');

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this._setStatus('connected');
      };

      this.ws.onmessage = (event) => {
        try {
          const data: WebSocketSnapshotMessage = JSON.parse(event.data);
          if (this.onMessageCallback) {
            this.onMessageCallback(data);
          }
        } catch (err) {
          console.error('[WebSocket] Failed to parse snapshot message:', err);
        }
      };

      this.ws.onerror = () => {
        this._setStatus('error', 'WebSocket connection error');
      };

      this.ws.onclose = (event) => {
        if (this.isIntentionallyClosed) {
          this._setStatus('disconnected', 'Session closed');
          return;
        }

        if (event.code === 4004) {
          this._setStatus('error', `Run '${this.runId}' not found`);
          return;
        }

        if (event.code === 4003) {
          this._setStatus('error', 'Disallowed browser origin');
          return;
        }

        this._handleReconnect();
      };
    } catch (err: any) {
      this._setStatus('error', err?.message || 'Connection initiation failed');
      this._handleReconnect();
    }
  }

  private _handleReconnect(): void {
    if (this.isIntentionallyClosed) return;

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this._setStatus('error', `Reconnection failed after ${this.maxReconnectAttempts} attempts`);
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.initialBackoffMs * Math.pow(1.5, this.reconnectAttempts - 1),
      this.maxBackoffMs
    );

    this._setStatus(
      'reconnecting',
      `Reconnecting in ${(delay / 1000).toFixed(1)}s (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`
    );

    this.reconnectTimer = setTimeout(() => {
      this._initiateConnection();
    }, delay);
  }

  private _setStatus(status: ConnectionStatus, detail?: string): void {
    this.status = status;
    if (this.onStatusChangeCallback) {
      this.onStatusChangeCallback(status, detail);
    }
  }
}
