"""
SMS Dev Server - Local SMS Capture and Viewer

A lightweight development server that captures SMS messages locally
and displays them in a web UI, similar to MailDev for emails.

Run: python scripts/sms_dev_server.py
View: http://localhost:1080
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from datetime import datetime
import uuid
import json
import os

# Disable Flask's automatic .env file loading to prevent parsing errors
os.environ['FLASK_SKIP_DOTENV'] = '1'

app = Flask(__name__)
CORS(app)  # Allow CORS for API calls from backend

# In-memory storage for SMS messages
messages = []

# HTML template for the SMS viewer UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMS Dev Server - Local SMS Viewer</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f7;
            color: #1d1d1f;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 5px;
        }
        
        .header p {
            font-size: 14px;
            opacity: 0.9;
        }
        
        .stats {
            display: flex;
            gap: 20px;
            padding: 20px;
            background: white;
            border-bottom: 1px solid #e5e5e7;
        }
        
        .stat {
            flex: 1;
            text-align: center;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: 700;
            color: #667eea;
        }
        
        .stat-label {
            font-size: 12px;
            color: #86868b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 5px;
        }
        
        .controls {
            padding: 20px;
            background: white;
            border-bottom: 1px solid #e5e5e7;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .button {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .button-primary {
            background: #667eea;
            color: white;
        }
        
        .button-primary:hover {
            background: #5568d3;
            transform: translateY(-1px);
        }
        
        .button-danger {
            background: #ff3b30;
            color: white;
        }
        
        .button-danger:hover {
            background: #e6342a;
        }
        
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 14px;
            color: #86868b;
        }
        
        .auto-refresh input {
            cursor: pointer;
        }
        
        .messages {
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        
        .message {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .message:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        }
        
        .message-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e5e5e7;
        }
        
        .message-meta {
            display: flex;
            gap: 20px;
        }
        
        .meta-item {
            display: flex;
            flex-direction: column;
        }
        
        .meta-label {
            font-size: 11px;
            color: #86868b;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 3px;
        }
        
        .meta-value {
            font-size: 14px;
            font-weight: 600;
            color: #1d1d1f;
        }
        
        .message-sid {
            font-size: 11px;
            color: #86868b;
            font-family: monospace;
        }
        
        .message-body {
            background: #f5f5f7;
            padding: 15px;
            border-radius: 8px;
            font-size: 15px;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .message-footer {
            display: flex;
            gap: 15px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e5e5e7;
        }
        
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .badge-success {
            background: #d1f4e0;
            color: #0e6b34;
        }
        
        .badge-info {
            background: #d6e9ff;
            color: #0055cc;
        }
        
        .badge-warning {
            background: #fff3cd;
            color: #856404;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
        }
        
        .empty-state svg {
            width: 80px;
            height: 80px;
            margin-bottom: 20px;
            opacity: 0.3;
        }
        
        .empty-state h2 {
            font-size: 20px;
            color: #86868b;
            margin-bottom: 10px;
        }
        
        .empty-state p {
            font-size: 14px;
            color: #b0b0b5;
        }
        
        .timestamp {
            color: #86868b;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📱 SMS Dev Server</h1>
        <p>Local SMS capture and viewer - No real SMS delivered</p>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="stat-value" id="total-messages">0</div>
            <div class="stat-label">Total Messages</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="total-chars">0</div>
            <div class="stat-label">Total Characters</div>
        </div>
        <div class="stat">
            <div class="stat-value" id="total-segments">0</div>
            <div class="stat-label">SMS Segments</div>
        </div>
    </div>
    
    <div class="controls">
        <div class="auto-refresh">
            <input type="checkbox" id="auto-refresh" checked>
            <label for="auto-refresh">Auto-refresh every 2 seconds</label>
        </div>
        <div style="display: flex; gap: 10px;">
            <button class="button button-primary" onclick="refreshMessages()">🔄 Refresh</button>
            <button class="button button-danger" onclick="clearMessages()">🗑️ Clear All</button>
        </div>
    </div>
    
    <div class="messages" id="messages">
        <div class="empty-state">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
            </svg>
            <h2>No messages yet</h2>
            <p>Send an SMS from the dashboard and it will appear here</p>
        </div>
    </div>
    
    <script>
        let autoRefreshInterval = null;
        
        async function refreshMessages() {
            try {
                const response = await fetch('/api/messages');
                const data = await response.json();
                
                updateStats(data.messages);
                renderMessages(data.messages);
            } catch (error) {
                console.error('Error fetching messages:', error);
            }
        }
        
        function updateStats(messages) {
            document.getElementById('total-messages').textContent = messages.length;
            
            const totalChars = messages.reduce((sum, msg) => sum + msg.body.length, 0);
            document.getElementById('total-chars').textContent = totalChars;
            
            const totalSegments = messages.reduce((sum, msg) => sum + Math.ceil(msg.body.length / 160), 0);
            document.getElementById('total-segments').textContent = totalSegments;
        }
        
        function renderMessages(messages) {
            const container = document.getElementById('messages');
            
            if (messages.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                        </svg>
                        <h2>No messages yet</h2>
                        <p>Send an SMS from the dashboard and it will appear here</p>
                    </div>
                `;
                return;
            }
            
            // Sort by timestamp descending (newest first)
            messages.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            
            container.innerHTML = messages.map(msg => {
                const segments = Math.ceil(msg.body.length / 160);
                const timestamp = new Date(msg.timestamp).toLocaleString();
                
                return `
                    <div class="message">
                        <div class="message-header">
                            <div class="message-meta">
                                <div class="meta-item">
                                    <div class="meta-label">From</div>
                                    <div class="meta-value">${msg.from}</div>
                                </div>
                                <div class="meta-item">
                                    <div class="meta-label">To</div>
                                    <div class="meta-value">${msg.to}</div>
                                </div>
                                <div class="meta-item">
                                    <div class="meta-label">Timestamp</div>
                                    <div class="meta-value timestamp">${timestamp}</div>
                                </div>
                            </div>
                            <div class="message-sid">SID: ${msg.sid}</div>
                        </div>
                        
                        <div class="message-body">${escapeHtml(msg.body)}</div>
                        
                        <div class="message-footer">
                            <span class="badge badge-success">✓ ${msg.status}</span>
                            <span class="badge badge-info">${msg.body.length} characters</span>
                            <span class="badge ${segments > 1 ? 'badge-warning' : 'badge-info'}">${segments} segment${segments > 1 ? 's' : ''}</span>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        async function clearMessages() {
            if (!confirm('Clear all messages?')) return;
            
            try {
                await fetch('/api/messages', { method: 'DELETE' });
                refreshMessages();
            } catch (error) {
                console.error('Error clearing messages:', error);
            }
        }
        
        // Auto-refresh toggle
        document.getElementById('auto-refresh').addEventListener('change', (e) => {
            if (e.target.checked) {
                autoRefreshInterval = setInterval(refreshMessages, 2000);
            } else {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                }
            }
        });
        
        // Initial load and auto-refresh
        refreshMessages();
        autoRefreshInterval = setInterval(refreshMessages, 2000);
    </script>
</body>
</html>
"""

# API Routes

@app.route('/')
def index():
    """Serve the SMS viewer UI"""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/messages', methods=['GET'])
def get_messages():
    """Get all captured SMS messages"""
    return jsonify({
        'success': True,
        'count': len(messages),
        'messages': messages
    })


@app.route('/api/messages', methods=['DELETE'])
def clear_messages():
    """Clear all captured SMS messages"""
    messages.clear()
    return jsonify({
        'success': True,
        'message': 'All messages cleared'
    })


@app.route('/2010-04-01/Accounts/<account_sid>/Messages.json', methods=['POST'])
def send_message(account_sid):
    """
    Twilio-compatible SMS endpoint
    
    Mimics Twilio's SMS API to capture messages sent from the application
    """
    # Extract SMS data from form data (Twilio sends as form-encoded)
    to = request.form.get('To', request.json.get('to') if request.is_json else None)
    from_ = request.form.get('From', request.json.get('from') if request.is_json else None)
    body = request.form.get('Body', request.json.get('body') if request.is_json else None)
    
    # Generate a fake message SID
    message_sid = f"SM{uuid.uuid4().hex[:32]}"
    
    # Store the message
    message = {
        'sid': message_sid,
        'account_sid': account_sid,
        'to': to,
        'from': from_,
        'body': body,
        'status': 'queued',
        'timestamp': datetime.now().isoformat(),
        'segments': len(body) // 160 + (1 if len(body) % 160 > 0 else 0) if body else 1
    }
    
    messages.append(message)
    
    print(f"\n📱 SMS Captured!")
    print(f"   From: {from_}")
    print(f"   To: {to}")
    print(f"   Body: {body[:50]}{'...' if len(body) > 50 else ''}")
    print(f"   SID: {message_sid}")
    print(f"   View at: http://localhost:1080\n")
    
    # Return Twilio-compatible response
    return jsonify({
        'sid': message_sid,
        'account_sid': account_sid,
        'to': to,
        'from': from_,
        'body': body,
        'status': 'queued',
        'date_created': datetime.now().isoformat(),
        'date_updated': datetime.now().isoformat(),
        'date_sent': None,
        'direction': 'outbound-api',
        'price': None,
        'price_unit': 'USD',
        'uri': f'/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}.json'
    }), 201


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'SMS Dev Server',
        'messages_count': len(messages)
    })


if __name__ == '__main__':
    # Configure UTF-8 encoding for Windows console to support emoji characters
    import sys
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("\n" + "=" * 70)
    print("🚀 SMS Dev Server Starting...")
    print("=" * 70)
    print(f"\n📱 SMS Viewer UI:  http://localhost:1081")
    print(f"🔌 API Endpoint:   http://localhost:1081/api/messages")
    print(f"💊 Health Check:   http://localhost:1081/health")
    print("\n💡 Set SMS_MODE=local in .env to use this server")
    print("=" * 70 + "\n")
    
    app.run(host='0.0.0.0', port=1081, debug=True, use_reloader=False)
