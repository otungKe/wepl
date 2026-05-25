/**
 * Generates a branded PDF receipt for a contribution transaction.
 * Uses expo-print to render HTML → PDF, then expo-sharing to let
 * the user save or share the file.
 */

import * as Print   from 'expo-print';
import * as Sharing from 'expo-sharing';
import { Alert }    from 'react-native';
import type { Transaction } from '../api/contributions';

const TX_LABEL: Record<string, string> = {
  CONTRIBUTION: 'Deposit',
  WITHDRAWAL:   'Withdrawal',
  ADVANCE:      'Emergency Advance',
  REPAYMENT:    'Loan Repayment',
};

const TX_COLOR: Record<string, string> = {
  CONTRIBUTION: '#1A5C38',
  WITHDRAWAL:   '#C0392B',
  ADVANCE:      '#C49A28',
  REPAYMENT:    '#1A5C38',
};

function fmt(date: Date) {
  return {
    date: date.toLocaleDateString('en-KE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }),
    time: date.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  };
}

function buildHtml(tx: Transaction, contributionTitle: string): string {
  const isCredit  = tx.transaction_type === 'CONTRIBUTION' || tx.transaction_type === 'REPAYMENT';
  const label     = TX_LABEL[tx.transaction_type] ?? tx.transaction_type;
  const color     = TX_COLOR[tx.transaction_type] ?? '#1A5C38';
  const sign      = isCredit ? '+' : '−';
  const amount    = Number(tx.amount).toLocaleString('en-KE', { minimumFractionDigits: 2 });
  const dt        = fmt(new Date(tx.created_at));
  const displayBy = tx.name ? `${tx.name} (${tx.phone_number})` : tx.phone_number;

  const row = (label: string, value: string, highlight = false) => `
    <tr>
      <td class="label">${label}</td>
      <td class="value${highlight ? ' highlight' : ''}">${value}</td>
    </tr>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>WEPL Receipt</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #F5F8F6;
    padding: 40px 24px;
    color: #111C16;
  }
  .card {
    background: #ffffff;
    border-radius: 16px;
    max-width: 480px;
    margin: 0 auto;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0,0,0,0.08);
  }
  /* Header strip */
  .header {
    background: ${color};
    padding: 32px 24px 24px;
    text-align: center;
  }
  .brand {
    font-size: 13px;
    color: rgba(255,255,255,0.75);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 16px;
  }
  .tx-type {
    font-size: 14px;
    color: rgba(255,255,255,0.85);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }
  .amount {
    font-size: 42px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: -1px;
  }
  .currency {
    font-size: 20px;
    font-weight: 400;
    vertical-align: super;
    margin-right: 4px;
  }
  .status-badge {
    display: inline-block;
    margin-top: 14px;
    padding: 4px 16px;
    border-radius: 99px;
    background: rgba(255,255,255,0.2);
    font-size: 12px;
    color: #fff;
    letter-spacing: 1px;
  }
  /* Detail table */
  .body { padding: 24px; }
  .section-title {
    font-size: 10px;
    letter-spacing: 1.5px;
    color: #8FA89A;
    text-transform: uppercase;
    margin-bottom: 12px;
  }
  table { width: 100%; border-collapse: collapse; }
  tr { border-bottom: 1px solid #EEF3EF; }
  tr:last-child { border-bottom: none; }
  td { padding: 11px 0; font-size: 13px; vertical-align: top; }
  .label { color: #8FA89A; width: 40%; }
  .value { color: #111C16; font-weight: 500; text-align: right; word-break: break-all; }
  .value.highlight { color: ${color}; font-weight: 700; font-family: monospace; font-size: 14px; }
  .mono { font-family: monospace; font-size: 13px; }
  /* Divider */
  .divider { border: none; border-top: 1px dashed #D8E5DC; margin: 20px 0; }
  /* Footer */
  .footer {
    text-align: center;
    padding: 16px 24px 24px;
    border-top: 1px solid #EEF3EF;
  }
  .footer p { font-size: 11px; color: #8FA89A; }
  .footer .platform { font-size: 12px; color: #4D6358; font-weight: 600; margin-bottom: 4px; }
  .watermark {
    font-size: 9px;
    color: #D8E5DC;
    margin-top: 8px;
    letter-spacing: 1px;
  }
</style>
</head>
<body>
<div class="card">
  <!-- Header -->
  <div class="header">
    <div class="brand">WEPL · Wallet</div>
    <div class="tx-type">${label}</div>
    <div class="amount">
      <span class="currency">KES</span>${sign}&nbsp;${amount}
    </div>
    <span class="status-badge">✓ CONFIRMED</span>
  </div>

  <!-- Body -->
  <div class="body">
    <div class="section-title">Transaction Details</div>
    <table>
      ${row('Date', dt.date)}
      ${row('Time', dt.time)}
      ${row('By', displayBy)}
      ${row('Group', contributionTitle)}
      ${tx.note ? row('Note', tx.note) : ''}
    </table>

    <hr class="divider"/>

    <div class="section-title">References</div>
    <table>
      ${row('Platform Ref', `<span class="mono">${tx.platform_ref}</span>`)}
      ${tx.mpesa_receipt
        ? row('M-Pesa Ref',  `<span class="mono">${tx.mpesa_receipt}</span>`, true)
        : row('M-Pesa Ref', '—')
      }
    </table>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p class="platform">WEPL Financial Platform</p>
    <p>Generated ${new Date().toLocaleString('en-KE')}</p>
    <p class="watermark">This is an official transaction receipt. Please keep it for your records.</p>
  </div>
</div>
</body>
</html>`;
}

export async function downloadReceipt(tx: Transaction, contributionTitle: string): Promise<void> {
  try {
    const html = buildHtml(tx, contributionTitle);
    const { uri } = await Print.printToFileAsync({ html, base64: false });

    const canShare = await Sharing.isAvailableAsync();
    if (!canShare) {
      Alert.alert('Not supported', 'File sharing is not available on this device.');
      return;
    }

    const filename = `WEPL-Receipt-${tx.platform_ref}.pdf`;
    await Sharing.shareAsync(uri, {
      mimeType:   'application/pdf',
      dialogTitle: `Save or share receipt`,
      UTI:        'com.adobe.pdf',
    });
  } catch (err: any) {
    Alert.alert('Error', err?.message ?? 'Could not generate receipt. Please try again.');
  }
}
