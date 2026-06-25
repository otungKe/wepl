import { useState, useEffect, useCallback, useRef } from "react";
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ActivityIndicator, Alert, ScrollView, Modal, Share,
  KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getContribution, getParticipants, leaveContribution,
  closeContribution, reopenContribution, archiveContribution, deleteContribution,
  updateContribution,
  getDisbursements, createDisbursement, voteDisbursement, cancelDisbursementRequest,
  getContributionTransactions,
  getStandingOrders, createStandingOrder, executeStandingOrder, cancelStandingOrder, updateStandingOrder,
  UpdateStandingOrderPayload,
  getAmendments, proposeAmendment, voteAmendment, withdrawAmendment,
  requestJoinContribution, getPendingJoinRequests, actionJoinRequest,
  inviteMemberToContribution, respondToContributionInvite,
  getMyContributionJoinRequest, getMyContributionInvite,
  Contribution, Participant, DisbursementRequest, Transaction,
  StandingOrder as StandingOrderType,
  ContributionAmendment, ContributionJoinRequest as ContribJoinRequest,
} from "../../api/contributions";
import * as storage from "../../utils/secureStorage";
import { downloadReceipt } from "../../utils/receipt";
import { initiateSTKPush, checkSTKStatus } from "../../api/mpesa";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import AppHeader from "../../components/app/AppHeader";
import Avatar from "../../components/app/Avatar";
import { useKYCGate } from "../../hooks/useKYCGate";

type TabKey = 'members' | 'transactions' | 'disbursements' | 'amendments';

const TX_COLOR: Record<string, string> = {
  CONTRIBUTION: COLORS.success,
  WITHDRAWAL:   COLORS.error,
  ADVANCE:      COLORS.accent,
  REPAYMENT:    COLORS.primary,
};

const TX_LABEL: Record<string, string> = {
  CONTRIBUTION: 'Deposit',
  WITHDRAWAL:   'Withdrawal',
  ADVANCE:      'Emergency Advance',
  REPAYMENT:    'Loan Repayment',
};

function statusBg(s: string) {
  switch (s) {
    case 'APPROVED': case 'EXECUTED': case 'DISBURSED': case 'REPAID':
      return { backgroundColor: COLORS.primaryPale };
    case 'REJECTED':
      return { backgroundColor: '#fce8e6' };
    case 'WITHDRAWN':
      return { backgroundColor: '#f3f4f6' };
    default:
      return { backgroundColor: '#fef7e0' };
  }
}

// ---------------------------------------------------------------------------
// Transaction detail helper
// ---------------------------------------------------------------------------
function TxDetailRow({
  label, value, mono = false, highlight = false,
}: {
  label: string; value: string; mono?: boolean; highlight?: boolean;
}) {
  return (
    <View style={txDetailStyles.row}>
      <Text style={txDetailStyles.rowLabel}>{label}</Text>
      <Text
        style={[
          txDetailStyles.rowValue,
          mono      && txDetailStyles.mono,
          highlight && txDetailStyles.highlight,
        ]}
        selectable
      >
        {value}
      </Text>
    </View>
  );
}

const txDetailStyles = StyleSheet.create({
  table:     { borderRadius: RADIUS.md, backgroundColor: COLORS.surface, overflow: 'hidden' },
  row:       { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: COLORS.divider },
  rowLabel:  { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: '400' as const, flex: 1 },
  rowValue:  { fontSize: FONTS.sm, color: COLORS.text, fontWeight: '500' as const, flex: 2, textAlign: 'right' as const },
  mono:      { fontFamily: 'monospace' as const, letterSpacing: 0.5 },
  highlight: { color: COLORS.primary, fontWeight: '700' as const },
});

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------
export default function ContributionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const contributionId = Number(id);

  const [contribution, setContribution]   = useState<Contribution | null>(null);
  const [participants, setParticipants]   = useState<Participant[]>([]);
  const [standingOrders, setStandingOrders] = useState<StandingOrderType[]>([]);
  const [disbursements, setDisbursements]   = useState<DisbursementRequest[]>([]);
  const [transactions, setTransactions]     = useState<Transaction[]>([]);
  const [amendments, setAmendments]         = useState<ContributionAmendment[]>([]);
  const [joinRequests, setJoinRequests]     = useState<ContribJoinRequest[]>([]);
  const [myJoinRequest, setMyJoinRequest]   = useState<ContribJoinRequest | null>(null);
  const [myInvite, setMyInvite]             = useState<ContribJoinRequest | null>(null);
  const [showInvite, setShowInvite]         = useState(false);
  const [invitePhone, setInvitePhone]       = useState("");
  const [inviteSending, setInviteSending]   = useState(false);

  const [loading, setLoading]   = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [forbidden, setForbidden] = useState(false);
  const [nonParticipantPreview, setNonParticipantPreview] = useState<{ id: number; title: string; status: string } | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('transactions');
  const [showMenu, setShowMenu] = useState(false);
  const [myPhone, setMyPhone]   = useState("");
  const [myName, setMyName]     = useState("");

  // Modals
  const [showMpesa, setShowMpesa]               = useState(false);
  const [showDisbursement, setShowDisbursement] = useState(false);
  const [showStandingOrder, setShowStandingOrder] = useState(false);
  const [showManageOrders, setShowManageOrders] = useState(false);

  // Standing order form state
  const [soAmount, setSoAmount]       = useState("");
  const [soFrequency, setSoFrequency] = useState<'daily'|'weekly'|'monthly'>('monthly');
  const [soPayeeType, setSoPayeeType] = useState<'fixed'|'rotating'>('fixed');
  const [soPhone, setSoPhone]         = useState("");

  // Transaction detail sheet
  const [selectedTx, setSelectedTx]           = useState<Transaction | null>(null);
  const [downloadingReceipt, setDownloading]  = useState(false);

  const { requireKYC } = useKYCGate();

  // Edit standing order modal
  const [showEditOrder, setShowEditOrder]       = useState(false);
  const [editOrderId, setEditOrderId]           = useState<number | null>(null);
  const [editOrderPayeeType, setEditOrderPayeeType] = useState<'fixed'|'rotating'>('fixed');
  const [editOrderAmount, setEditOrderAmount]   = useState("");
  const [editOrderFreq, setEditOrderFreq]       = useState<'daily'|'weekly'|'monthly'>('monthly');
  const [editOrderPhone, setEditOrderPhone]     = useState("");
  const [editOrderSaving, setEditOrderSaving]   = useState(false);

  // Form state
  const [amount, setAmount]               = useState("");
  const [disbReason, setDisbReason]       = useState("");
  const [disbRecipient, setDisbRecipient] = useState("");
  const [mpesaPhone, setMpesaPhone]       = useState("");
  const [mpesaPolling, setMpesaPolling]   = useState(false);
  const [submitting, setSubmitting]       = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Direct edit modal (cosmetic: title + description)
  const [showEdit, setShowEdit]   = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc]   = useState("");
  const [editSaving, setEditSaving] = useState(false);

  // Amendment proposal modal (sensitive fields)
  const [showAmend, setShowAmend]           = useState(false);
  const [amendTarget, setAmendTarget]       = useState("");
  const [amendEndDate, setAmendEndDate]     = useState("");
  const [amendPeriod, setAmendPeriod]       = useState("");
  const [amendFixed, setAmendFixed]         = useState("");
  const [amendThreshold, setAmendThreshold] = useState<string>("");
  const [amendVisibility, setAmendVisibility] = useState<'closed'|'open'>('closed');
  const [amendReason, setAmendReason]       = useState("");
  const [amendSaving, setAmendSaving]       = useState(false);

  useEffect(() => {
    storage.multiGet(["phone", "name"]).then(([phoneEntry, nameEntry]) => {
      if (phoneEntry[1]) setMyPhone(phoneEntry[1]);
      if (nameEntry[1])  setMyName(nameEntry[1]);
    });
    // Cleanup poll interval on unmount
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const c = await getContribution(contributionId);
      // Success means the user is a participant — clear any prior non-participant state.
      setContribution(c);
      setNonParticipantPreview(null);
      setForbidden(false);

      const [p, txs, disbs, orders, amends] = await Promise.all([
        getParticipants(contributionId),
        getContributionTransactions(contributionId),
        getDisbursements(contributionId),
        getStandingOrders(contributionId),
        getAmendments(contributionId),
      ]);
      setParticipants(p);
      setTransactions(txs);
      setDisbursements(disbs);
      setStandingOrders(orders);
      setAmendments(amends);

      try {
        const jrs = await getPendingJoinRequests(contributionId);
        setJoinRequests(jrs);
      } catch {}
      try {
        const [myReq, myInv] = await Promise.all([
          getMyContributionJoinRequest(contributionId),
          getMyContributionInvite(contributionId),
        ]);
        setMyJoinRequest(myReq);
        setMyInvite(myInv);
      } catch {}
    } catch (e: any) {
      if (e?.response?.status === 404) {
        setNotFound(true);
      } else if (e?.response?.status === 403) {
        const errData = e.response?.data;
        if (errData?.error === "not_participant") {
          setNonParticipantPreview({ id: errData.id, title: errData.title, status: errData.status });
          // Load the user's own join request / invite so the screen can show the right CTA.
          try {
            const [myReq, myInv] = await Promise.all([
              getMyContributionJoinRequest(contributionId),
              getMyContributionInvite(contributionId),
            ]);
            setMyJoinRequest(myReq);
            setMyInvite(myInv);
          } catch {}
        } else {
          setForbidden(true);
        }
      }
    }
  }, [contributionId]);

  useEffect(() => { load().finally(() => setLoading(false)); }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleMpesaPush = async () => {
    if (!amount || Number(amount) <= 0) {
      Alert.alert("Invalid amount", "Enter a valid amount.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await initiateSTKPush({
        contribution_id: contributionId,
        amount: Number(amount),
        phone_number: mpesaPhone || undefined,
      });
      setShowMpesa(false);
      setMpesaPolling(true);
      const checkoutId = result.checkout_request_id;
      let attempts = 0;
      let fired     = false;   // ensure Alert fires at most once per payment

      // Capture the interval ID in the closure — NOT via pollRef — so that
      // clearInterval always references the correct ID even if the component
      // unmounts and pollRef.current is reset to null.
      let intervalId: ReturnType<typeof setInterval>;

      const stopPolling = () => {
        clearInterval(intervalId);
        pollRef.current = null;
        setMpesaPolling(false);
      };

      intervalId = setInterval(async () => {
        attempts++;
        try {
          const s = await checkSTKStatus(checkoutId);

          if (s.status === 'SUCCESS') {
            stopPolling();
            if (!fired) {
              fired = true;
              await load();
              Alert.alert("Payment received", `M-Pesa receipt: ${s.mpesa_receipt}`);
            }
          } else if (s.status === 'FAILED' || attempts >= 12) {
            stopPolling();
            if (!fired) {
              fired = true;
              if (s.status === 'FAILED') {
                Alert.alert("Payment failed", "M-Pesa payment was not completed. Please try again.");
              } else {
                Alert.alert("Payment pending", "We couldn't confirm the payment yet. Check your M-Pesa messages — if deducted, it will reflect shortly.");
              }
            }
          }
        } catch {
          stopPolling();
        }
      }, 5000);

      pollRef.current = intervalId;
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "STK push failed.");
    } finally {
      setSubmitting(false);
      setAmount("");
    }
  };

  const handleCreateStandingOrder = async () => {
    if (!soAmount || Number(soAmount) <= 0) { Alert.alert("Required", "Enter a valid amount."); return; }
    if (soPayeeType === 'fixed' && !soPhone.trim()) { Alert.alert("Required", "Enter the payee phone number."); return; }
    setSubmitting(true);
    try {
      await createStandingOrder(contributionId, {
        amount: Number(soAmount),
        frequency: soFrequency,
        payee_type: soPayeeType,
        fixed_payee_phone: soPayeeType === 'fixed' ? soPhone.trim() : undefined,
      });
      setShowStandingOrder(false);
      setSoAmount(""); setSoPhone(""); setSoFrequency('monthly'); setSoPayeeType('fixed');
      const orders = await getStandingOrders(contributionId);
      setStandingOrders(orders);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to create standing order.");
    } finally { setSubmitting(false); }
  };

  const handleExecuteOrder = async (orderId: number) => {
    try {
      await executeStandingOrder(orderId);
      const orders = await getStandingOrders(contributionId);
      setStandingOrders(orders);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    }
  };

  const handleCancelOrder = async (orderId: number) => {
    try {
      await cancelStandingOrder(orderId);
      setStandingOrders((prev) => prev.map((o) => o.id === orderId ? { ...o, is_active: false } : o));
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    }
  };

  const handleOpenEditOrder = (order: StandingOrderType) => {
    setEditOrderId(order.id);
    setEditOrderAmount(String(order.amount));
    setEditOrderFreq(order.frequency as 'daily'|'weekly'|'monthly');
    setEditOrderPhone(order.fixed_payee_phone || "");
    setEditOrderPayeeType(order.payee_type);
    setShowEditOrder(true);
  };

  const handleSaveEditOrder = async () => {
    if (!editOrderId) return;
    if (!editOrderAmount || Number(editOrderAmount) <= 0) {
      Alert.alert("Invalid amount", "Enter a positive amount.");
      return;
    }
    setEditOrderSaving(true);
    const payload: UpdateStandingOrderPayload = {
      amount: Number(editOrderAmount),
      frequency: editOrderFreq,
    };
    if (editOrderPayeeType === 'fixed') payload.fixed_payee_phone = editOrderPhone.trim() || null;
    try {
      await updateStandingOrder(editOrderId, payload);
      setShowEditOrder(false);
      const orders = await getStandingOrders(contributionId);
      setStandingOrders(orders);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to update standing order.");
    } finally {
      setEditOrderSaving(false);
    }
  };

  const handleCancelDisbursement = async (requestId: number) => {
    try {
      const updated = await cancelDisbursementRequest(requestId);
      setDisbursements((prev) => prev.map((d) => (d.id === requestId ? updated : d)));
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to cancel request.");
    }
  };

  const handleCreateDisbursement = async () => {
    if (!amount || !disbReason) {
      Alert.alert("Required", "Amount and reason are required.");
      return;
    }
    setSubmitting(true);
    try {
      await createDisbursement(contributionId, { amount: Number(amount), reason: disbReason, recipient_phone: disbRecipient });
      setShowDisbursement(false);
      setAmount(""); setDisbReason(""); setDisbRecipient("");
      await load();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    } finally { setSubmitting(false); }
  };

  const handleClose = async () => {
    setShowMenu(false);
    try {
      const updated = contribution?.status === 'closed'
        ? await reopenContribution(contributionId)
        : await closeContribution(contributionId);
      setContribution(updated);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    }
  };

  const handleArchive = async () => {
    setShowMenu(false);
    try {
      await archiveContribution(contributionId);
      router.back();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    }
  };

  const handleDelete = async () => {
    setShowMenu(false);
    try {
      await deleteContribution(contributionId);
      router.back();
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed.");
    }
  };

  const handleShare = async () => {
    if (!contribution) return;
    try {
      await Share.share({
        message: `Join "${contribution.title}" on Wepl!\nInvite code: ${contribution.invite_code}`,
      });
    } catch {}
  };

  const handleEditOpen = () => {
    if (!contribution) return;
    setEditTitle(contribution.title);
    setEditDesc(contribution.description ?? "");
    setShowEdit(true);
  };

  const handleSaveEdit = async () => {
    if (!editTitle.trim()) { Alert.alert("Required", "Title cannot be empty."); return; }
    setEditSaving(true);
    try {
      const updated = await updateContribution(contributionId, {
        title: editTitle.trim(),
        description: editDesc.trim() || undefined,
      });
      setContribution(updated);
      setShowEdit(false);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to update contribution.");
    } finally {
      setEditSaving(false);
    }
  };

  const handleAmendOpen = () => {
    if (!contribution) return;
    setAmendTarget(contribution.target_amount ? String(Number(contribution.target_amount)) : "");
    setAmendEndDate(contribution.end_date ?? "");
    setAmendPeriod(contribution.period_months ? String(contribution.period_months) : "");
    setAmendFixed(contribution.fixed_amount ? String(Number(contribution.fixed_amount)) : "");
    setAmendThreshold(contribution.voting_threshold);
    setAmendVisibility(contribution.visibility);
    setAmendReason("");
    setShowAmend(true);
  };

  const handleSubmitAmendment = async () => {
    if (!contribution) return;
    const changes: Record<string, any> = {};
    if (amendTarget    && amendTarget    !== String(Number(contribution.target_amount ?? "")))   changes.target_amount    = Number(amendTarget);
    if (amendFixed     && contribution.amount_type === 'fixed' && amendFixed !== String(Number(contribution.fixed_amount ?? ""))) changes.fixed_amount = Number(amendFixed);
    if (amendEndDate   && contribution.tenure_type === 'date'   && amendEndDate   !== (contribution.end_date ?? ""))   changes.end_date      = amendEndDate;
    if (amendPeriod    && contribution.tenure_type === 'period' && String(Number(amendPeriod)) !== String(contribution.period_months ?? "")) changes.period_months = Number(amendPeriod);
    if (amendThreshold !== contribution.voting_threshold)   changes.voting_threshold = amendThreshold;
    if (amendVisibility !== contribution.visibility)        changes.visibility       = amendVisibility;

    if (Object.keys(changes).length === 0) {
      Alert.alert("No changes", "Nothing was changed from the current values."); return;
    }
    if (!amendReason.trim()) { Alert.alert("Required", "Please explain the reason for this change."); return; }

    setAmendSaving(true);
    try {
      const amendment = await proposeAmendment(contributionId, { changes, reason: amendReason.trim() });
      setAmendments((prev) => [amendment, ...prev]);
      setShowAmend(false);
      setActiveTab('amendments');
      Alert.alert("Proposal submitted", `Your amendment has been sent to the group for a vote. ${amendment.required_approvals} approval(s) needed.`);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to submit amendment.");
    } finally {
      setAmendSaving(false);
    }
  };

  const handleVoteAmendment = async (amendmentId: number, vote: 'APPROVE' | 'REJECT') => {
    try {
      const updated = await voteAmendment(amendmentId, vote);
      setAmendments((prev) => prev.map((a) => a.id === amendmentId ? updated : a));
      if (updated.status === 'APPROVED') {
        await load(); // refresh contribution to show applied changes
        // UI reloads via load() — no extra alert needed
      }
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Vote failed.");
    }
  };

  const handleRequestJoin = async () => {
    try {
      const jr = await requestJoinContribution(contributionId);
      setMyJoinRequest(jr);
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Could not send join request.");
    }
  };

  const handleInviteSend = async () => {
    if (!invitePhone.trim()) { Alert.alert("Required", "Enter a phone number."); return; }
    setInviteSending(true);
    try {
      await inviteMemberToContribution(contributionId, invitePhone.trim());
      setShowInvite(false);
      setInvitePhone("");
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Could not send invitation.");
    } finally {
      setInviteSending(false);
    }
  };

  const handleActionJoinRequest = async (requestId: number, action: 'approve' | 'reject') => {
    try {
      await actionJoinRequest(requestId, action);
      // Optimistically remove from the pending list immediately
      setJoinRequests((prev) => prev.filter((r) => r.id !== requestId));
      if (action === 'approve') {
        // Refresh participants + contribution (member count) so the new member appears instantly
        await load();
      }
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Action failed.");
    }
  };

  const handleRespondInvite = async (action: 'accept' | 'decline') => {
    if (!myInvite) return;
    try {
      const updated = await respondToContributionInvite(myInvite.id, action);
      setMyInvite(null);
      if (action === 'accept') {
        await load();
      } else {
        // UI updates via load()/setMyInvite — no extra alert needed
      }
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Could not process response.");
    }
  };

  const handleWithdrawAmendment = async (amendmentId: number) => {
    try {
      const updated = await withdrawAmendment(amendmentId);
      setAmendments((prev) => prev.map((a) => a.id === amendmentId ? updated : a));
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Could not withdraw proposal.");
    }
  };

  if (loading || (!contribution && !notFound && !forbidden && !nonParticipantPreview)) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Contribution" variant="light" leading="back" />
        <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      </SafeAreaView>
    );
  }

  if (notFound) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Contribution" variant="light" leading="back" />
        <View style={[styles.center, { paddingHorizontal: 32, gap: 12 }]}>
          <Ionicons name="wallet-outline" size={56} color={COLORS.textMuted} />
          <Text style={{ fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text }}>Contribution not found</Text>
          <Text style={{ fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 }}>
            This contribution may have been deleted or is no longer available.
          </Text>
          <TouchableOpacity
            style={{ marginTop: 8, paddingHorizontal: 28, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary }}
            onPress={() => router.back()}
          >
            <Text style={{ color: COLORS.white, fontWeight: "700", fontSize: FONTS.md }}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (forbidden) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title="Contribution" variant="light" leading="back" />
        <View style={[styles.center, { paddingHorizontal: 32, gap: 12 }]}>
          <Ionicons name="lock-closed-outline" size={56} color={COLORS.textMuted} />
          <Text style={{ fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text }}>Members only</Text>
          <Text style={{ fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 }}>
            You must be a member of this community to view or join this contribution.
          </Text>
          <TouchableOpacity
            style={{ marginTop: 8, paddingHorizontal: 28, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary }}
            onPress={() => router.back()}
          >
            <Text style={{ color: COLORS.white, fontWeight: "700", fontSize: FONTS.md }}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  if (nonParticipantPreview) {
    return (
      <SafeAreaView style={styles.safe}>
        <AppHeader title={nonParticipantPreview.title} variant="light" leading="back" />
        <ScrollView contentContainerStyle={{ paddingHorizontal: 24, paddingTop: 40, paddingBottom: 40, alignItems: "center", gap: 16 }}>
          <Ionicons name="people-outline" size={60} color={COLORS.textMuted} />
          <Text style={{ fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, textAlign: "center" }}>
            {nonParticipantPreview.title}
          </Text>
          <Text style={{ fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 }}>
            This is a private savings group. Request to join and an admin will review your request.
          </Text>

          {/* Invite banner */}
          {myInvite && (
            <View style={[styles.inviteBanner, { marginTop: 8 }]}>
              <Ionicons name="mail-open-outline" size={20} color={COLORS.primary} />
              <View style={{ flex: 1 }}>
                <Text style={styles.inviteBannerTitle}>You've been invited to join</Text>
                <Text style={styles.inviteBannerSub}>
                  {myInvite.invited_by_phone} invited you to participate in this contribution.
                </Text>
              </View>
              <View style={{ gap: 6 }}>
                <TouchableOpacity style={styles.inviteAcceptBtn} onPress={() => handleRespondInvite('accept')}>
                  <Text style={styles.inviteAcceptText}>Accept</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.inviteDeclineBtn} onPress={() => handleRespondInvite('decline')}>
                  <Text style={styles.inviteDeclineText}>Decline</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Pending request banner */}
          {!myInvite && myJoinRequest?.status === 'PENDING' && (
            <View style={[styles.requestPendingBanner, { marginTop: 8 }]}>
              <Ionicons name="time-outline" size={18} color={COLORS.accent} />
              <Text style={styles.requestPendingText}>Join request pending — awaiting admin review</Text>
            </View>
          )}

          {/* Rejected banner */}
          {!myInvite && myJoinRequest?.status === 'REJECTED' && (
            <View style={[styles.requestPendingBanner, { backgroundColor: '#fce8e6', marginTop: 8 }]}>
              <Ionicons name="close-circle-outline" size={18} color={COLORS.error} />
              <Text style={[styles.requestPendingText, { color: COLORS.error }]}>
                Your previous request was declined. You can request again below.
              </Text>
            </View>
          )}

          {/* Request to join button */}
          {!myInvite && myJoinRequest?.status !== 'PENDING' && (
            <TouchableOpacity style={[styles.requestJoinBtn, { marginTop: 8 }]} onPress={handleRequestJoin}>
              <Ionicons name="person-add-outline" size={18} color={COLORS.primary} />
              <Text style={styles.requestJoinText}>Request to Join</Text>
            </TouchableOpacity>
          )}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // Narrow type — unreachable at runtime but needed for TypeScript after the compound guard above
  if (!contribution) return null;

  const isCreator     = contribution.created_by === myPhone;
  // is_admin from the API: true for creator OR community admin/treasurer
  const isAdmin       = contribution.is_admin ?? isCreator;
  // Trust the API's authoritative flag (creator or active participant); fall back
  // to phone-matching only if the field is absent (older backend). Prevents showing
  // "Request to Join" to members when phone formats differ or the list is partial.
  const isParticipant = contribution.is_participant ?? participants.some((p) => p.phone_number === myPhone && p.is_active);
  const cur          = Number(contribution.current_amount);
  const tgt          = contribution.target_amount ? Number(contribution.target_amount) : 0;
  const pct          = tgt > 0 ? Math.min((cur / tgt) * 100, 100) : 0;
  const pendingAmendments   = amendments.filter((a) => a.status === 'PENDING').length;
  const pendingJoinRequests = joinRequests.length;
  const activeOrderCount    = standingOrders.filter((o) => o.is_active).length;
  const tabs: { key: TabKey; label: string; badge?: number }[] = [
    { key: 'transactions',  label: 'Activity' },
    { key: 'members',       label: 'Members', badge: pendingJoinRequests || undefined },
    { key: 'disbursements', label: 'Withdraw' },
    { key: 'amendments',    label: 'Amendments', badge: pendingAmendments },
  ];

  return (
    <SafeAreaView style={styles.safe}>
      <AppHeader
        title={contribution.title}
        variant="light"
        leading="back"
        rightIcon="more"
        onRightPress={() => setShowMenu(true)}
      />

      {/* 3-dots menu */}
      <Modal visible={showMenu} transparent animationType="fade">
        <TouchableOpacity style={styles.menuOverlay} onPress={() => setShowMenu(false)}>
          <View style={styles.menuBox}>
            <TouchableOpacity style={styles.menuItem} onPress={() => { setShowMenu(false); handleShare(); }}>
              <Ionicons name="share-outline" size={18} color={COLORS.text} />
              <Text style={styles.menuItemText}>Share invite code</Text>
            </TouchableOpacity>

            {/* Admin actions — available to creator AND community admins */}
            {isAdmin && (
              <>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={() => { setShowMenu(false); handleEditOpen(); }}>
                  <Ionicons name="create-outline" size={18} color={COLORS.text} />
                  <Text style={styles.menuItemText}>Edit Name / Description</Text>
                </TouchableOpacity>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={() => { setShowMenu(false); handleAmendOpen(); }}>
                  <Ionicons name="git-pull-request-outline" size={18} color={COLORS.primary} />
                  <Text style={[styles.menuItemText, { color: COLORS.primary }]}>Propose Amendment</Text>
                </TouchableOpacity>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={() => { setShowMenu(false); setShowInvite(true); }}>
                  <Ionicons name="person-add-outline" size={18} color={COLORS.primary} />
                  <Text style={[styles.menuItemText, { color: COLORS.primary }]}>Invite Member</Text>
                </TouchableOpacity>
              </>
            )}

            {/* Creator-only destructive actions */}
            {isCreator && (
              <>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={handleClose}>
                  <Ionicons
                    name={contribution.status === 'closed' ? "play-circle-outline" : "pause-circle-outline"}
                    size={18}
                    color={COLORS.text}
                  />
                  <Text style={styles.menuItemText}>
                    {contribution.status === 'closed' ? "Reopen" : "Close"}
                  </Text>
                </TouchableOpacity>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={handleArchive}>
                  <Ionicons name="archive-outline" size={18} color={COLORS.textSecondary} />
                  <Text style={[styles.menuItemText, { color: COLORS.textSecondary }]}>Archive</Text>
                </TouchableOpacity>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={handleDelete}>
                  <Ionicons name="trash-outline" size={18} color={COLORS.error} />
                  <Text style={[styles.menuItemText, { color: COLORS.error }]}>Delete</Text>
                </TouchableOpacity>
              </>
            )}

            {!isCreator && (
              <>
                <View style={styles.menuDivider} />
                <TouchableOpacity style={styles.menuItem} onPress={() => {
                  setShowMenu(false);
                  leaveContribution(contributionId)
                    .then(() => router.back())
                    .catch((e: any) => Alert.alert("Error", e?.response?.data?.error || "Could not leave contribution."));
                }}>
                  <Ionicons name="exit-outline" size={18} color={COLORS.error} />
                  <Text style={[styles.menuItemText, { color: COLORS.error }]}>Leave</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </TouchableOpacity>
      </Modal>

      {mpesaPolling && (
        <View style={styles.pollingBanner}>
          <ActivityIndicator size="small" color={COLORS.white} />
          <Text style={styles.pollingText}>Waiting for M-Pesa confirmation…</Text>
        </View>
      )}

      {/* Edit contribution modal */}
      <Modal visible={showEdit} transparent animationType="slide" onRequestClose={() => setShowEdit(false)}>
        <KeyboardAvoidingView style={{ flex: 1, justifyContent: "flex-end" }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setShowEdit(false)} />
          <View style={[styles.sheet, { maxHeight: '92%' }]}>
            <View style={styles.sheetHandle} />
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              <Text style={styles.sheetTitle}>Edit Contribution</Text>
              <Text style={[styles.sheetHint, { marginBottom: 16 }]}>
                Structural settings (frequency, amount type, tenure type) cannot be changed after creation.
              </Text>

              <Text style={editStyles.fieldLabel}>Title *</Text>
              <TextInput style={editStyles.input} value={editTitle} onChangeText={setEditTitle}
                placeholder="Contribution title" placeholderTextColor={COLORS.textMuted} maxLength={120} />

              <Text style={editStyles.fieldLabel}>Description</Text>
              <TextInput style={[editStyles.input, { height: 80, textAlignVertical: "top" }]}
                value={editDesc} onChangeText={setEditDesc} multiline
                placeholder="Optional description" placeholderTextColor={COLORS.textMuted} maxLength={500} />

              <Text style={[styles.sheetHint, { marginTop: 10 }]}>
                To change amounts, thresholds, or other settings use "Propose Amendment" from the menu.
              </Text>

              <TouchableOpacity
                style={[editStyles.saveBtn, editSaving && { opacity: 0.7 }]}
                onPress={handleSaveEdit}
                disabled={editSaving}
              >
                {editSaving
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={editStyles.saveBtnText}>Save Changes</Text>}
              </TouchableOpacity>
              <TouchableOpacity style={editStyles.cancelBtn} onPress={() => setShowEdit(false)}>
                <Text style={editStyles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Amendment proposal modal */}
      <Modal visible={showAmend} transparent animationType="slide" onRequestClose={() => setShowAmend(false)}>
        <KeyboardAvoidingView style={{ flex: 1, justifyContent: "flex-end" }} behavior={Platform.OS === "ios" ? "padding" : "height"}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setShowAmend(false)} />
          <View style={[styles.sheet, { maxHeight: '92%' }]}>
            <View style={styles.sheetHandle} />
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              <Text style={styles.sheetTitle}>Propose Amendment</Text>
              <Text style={[styles.sheetHint, { marginBottom: 16 }]}>
                Changes to sensitive settings require approval from {contribution?.voting_label} before taking effect. Unchanged fields are not included.
              </Text>

              {contribution?.amount_type === 'fixed' && (
                <>
                  <Text style={editStyles.fieldLabel}>Fixed Amount per Member (KES)</Text>
                  <TextInput style={editStyles.input} value={amendFixed} onChangeText={setAmendFixed}
                    placeholder={`Current: KES ${Number(contribution.fixed_amount ?? 0).toLocaleString()}`}
                    placeholderTextColor={COLORS.textMuted} keyboardType="numeric" />
                </>
              )}

              <Text style={editStyles.fieldLabel}>Target Amount (KES)</Text>
              <TextInput style={editStyles.input} value={amendTarget} onChangeText={setAmendTarget}
                placeholder={contribution?.target_amount ? `Current: KES ${Number(contribution.target_amount).toLocaleString()}` : "No target set"}
                placeholderTextColor={COLORS.textMuted} keyboardType="numeric" />

              {contribution?.tenure_type === 'date' && (
                <>
                  <Text style={editStyles.fieldLabel}>End Date (YYYY-MM-DD)</Text>
                  <TextInput style={editStyles.input} value={amendEndDate} onChangeText={setAmendEndDate}
                    placeholder={`Current: ${contribution.end_date ?? 'none'}`} placeholderTextColor={COLORS.textMuted} />
                </>
              )}

              {contribution?.tenure_type === 'period' && (
                <>
                  <Text style={editStyles.fieldLabel}>Period (months)</Text>
                  <TextInput style={editStyles.input} value={amendPeriod} onChangeText={setAmendPeriod}
                    placeholder={`Current: ${contribution?.period_months ?? 'none'} months`}
                    placeholderTextColor={COLORS.textMuted} keyboardType="numeric" />
                </>
              )}

              <Text style={editStyles.fieldLabel}>Approval Threshold</Text>
              <View style={editStyles.segRow}>
                {(['admins', '25', '50', '100'] as const).map((t) => (
                  <TouchableOpacity key={t} style={[editStyles.seg, amendThreshold === t && editStyles.segActive]}
                    onPress={() => setAmendThreshold(t)}>
                    <Text style={[editStyles.segText, amendThreshold === t && editStyles.segTextActive]}>
                      {t === 'admins' ? 'Admins' : `${t}%`}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={editStyles.fieldLabel}>Visibility</Text>
              <View style={editStyles.segRow}>
                {(['closed', 'open'] as const).map((v) => (
                  <TouchableOpacity key={v} style={[editStyles.seg, amendVisibility === v && editStyles.segActive]}
                    onPress={() => setAmendVisibility(v)}>
                    <Text style={[editStyles.segText, amendVisibility === v && editStyles.segTextActive]}>
                      {v === 'closed' ? 'Community only' : 'Public (Open)'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <Text style={editStyles.fieldLabel}>Reason for change *</Text>
              <TextInput style={[editStyles.input, { height: 80, textAlignVertical: "top" }]}
                value={amendReason} onChangeText={setAmendReason} multiline
                placeholder="Explain why this change is needed"
                placeholderTextColor={COLORS.textMuted} maxLength={500} />

              <TouchableOpacity style={[editStyles.saveBtn, amendSaving && { opacity: 0.7 }]}
                onPress={handleSubmitAmendment} disabled={amendSaving}>
                {amendSaving
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={editStyles.saveBtnText}>Submit for Group Vote</Text>}
              </TouchableOpacity>
              <TouchableOpacity style={editStyles.cancelBtn} onPress={() => setShowAmend(false)}>
                <Text style={editStyles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {contribution.status !== 'active' && (
        <View style={[styles.statusBanner, contribution.status === 'archived' && styles.statusBannerArchived]}>
          <Ionicons
            name={contribution.status === 'closed' ? "pause-circle-outline" : "archive-outline"}
            size={16}
            color={COLORS.white}
          />
          <Text style={styles.statusBannerText}>
            {contribution.status === 'closed'
              ? "This contribution is closed — no new activity allowed."
              : "This contribution has been archived."}
          </Text>
        </View>
      )}

      <ScrollView contentContainerStyle={{ paddingBottom: 32 }}>
        {/* Hero */}
        <View style={styles.hero}>
          <Text style={styles.heroAmount}>KES {cur.toLocaleString()}</Text>
          {tgt > 0 && (
            <>
              <View style={styles.progressBg}>
                <View style={[styles.progressFill, { width: `${pct}%` }]} />
              </View>
              <Text style={styles.progressLabel}>{Math.round(pct)}% of KES {tgt.toLocaleString()}</Text>
            </>
          )}
          {/* Config badges */}
          <View style={styles.heroBadges}>
            <View style={styles.heroBadge}>
              <Text style={styles.heroBadgeText}>{contribution.frequency.charAt(0).toUpperCase() + contribution.frequency.slice(1)}</Text>
            </View>
            <View style={styles.heroBadge}>
              <Text style={styles.heroBadgeText}>
                {contribution.amount_type === 'fixed' && contribution.fixed_amount
                  ? `KES ${Number(contribution.fixed_amount).toLocaleString()} fixed`
                  : 'Open amount'}
              </Text>
            </View>
            <View style={styles.heroBadge}>
              <Text style={styles.heroBadgeText}>{contribution.voting_label}</Text>
            </View>
            {contribution.tenure_type !== 'open' && (
              <View style={styles.heroBadge}>
                <Text style={styles.heroBadgeText}>
                  {contribution.tenure_type === 'date' && contribution.end_date
                    ? `Ends ${contribution.end_date}`
                    : contribution.tenure_type === 'period' && contribution.period_months
                    ? `${contribution.period_months}mo term`
                    : ''}
                </Text>
              </View>
            )}
          </View>
          <Text style={styles.heroMeta}>
            {contribution.participant_count} member{contribution.participant_count !== 1 ? 's' : ''}
          </Text>
        </View>

        {/* M-Pesa CTA — only for active participants */}
        {isParticipant && (
          <TouchableOpacity
            style={styles.mpesaBtn}
            onPress={() => { if (requireKYC()) setShowMpesa(true); }}
          >
            <Ionicons name="phone-portrait-outline" size={18} color={COLORS.white} />
            <Text style={styles.mpesaBtnText}>Pay with M-Pesa</Text>
          </TouchableOpacity>
        )}

        {/* Non-participant CTAs */}
        {!isParticipant && contribution.status === 'active' && (
          <>
            {/* Status banners (invite / pending / rejected) */}
            {myInvite && (
              <View style={styles.inviteBanner}>
                <Ionicons name="mail-open-outline" size={20} color={COLORS.primary} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.inviteBannerTitle}>You've been invited to join</Text>
                  <Text style={styles.inviteBannerSub}>
                    {myInvite.invited_by_phone} invited you to participate in this contribution.
                  </Text>
                </View>
                <View style={{ gap: 6 }}>
                  <TouchableOpacity style={styles.inviteAcceptBtn} onPress={() => handleRespondInvite('accept')}>
                    <Text style={styles.inviteAcceptText}>Accept</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.inviteDeclineBtn} onPress={() => handleRespondInvite('decline')}>
                    <Text style={styles.inviteDeclineText}>Decline</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
            {!myInvite && myJoinRequest?.status === 'PENDING' && (
              <View style={styles.requestPendingBanner}>
                <Ionicons name="time-outline" size={18} color={COLORS.accent} />
                <Text style={styles.requestPendingText}>Join request pending — awaiting admin review</Text>
              </View>
            )}
            {!myInvite && myJoinRequest?.status === 'REJECTED' && (
              <View style={[styles.requestPendingBanner, { backgroundColor: '#fce8e6' }]}>
                <Ionicons name="close-circle-outline" size={18} color={COLORS.error} />
                <Text style={[styles.requestPendingText, { color: COLORS.error }]}>Your previous request was declined. You can request again below.</Text>
              </View>
            )}

            {/* Request to join — same position and margin as the M-Pesa button */}
            {!myInvite && myJoinRequest?.status !== 'PENDING' && (
              <TouchableOpacity style={styles.requestJoinBtn} onPress={handleRequestJoin}>
                <Ionicons name="person-add-outline" size={18} color={COLORS.primary} />
                <Text style={styles.requestJoinText}>Request to Join</Text>
              </TouchableOpacity>
            )}
          </>
        )}

        {contribution.visibility === 'open' && (
          <TouchableOpacity style={styles.shareRow} onPress={handleShare}>
            <Ionicons name="link-outline" size={16} color={COLORS.primary} />
            <Text style={styles.shareText}>Invite code: <Text style={styles.shareCode}>{contribution.invite_code}</Text></Text>
          </TouchableOpacity>
        )}

        {/* Tab bar */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabScroll} contentContainerStyle={{ paddingHorizontal: 16, gap: 8 }}>
          {tabs.map((t) => (
            <TouchableOpacity
              key={t.key}
              style={[styles.tab, activeTab === t.key && styles.tabActive]}
              onPress={() => setActiveTab(t.key)}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <Text style={[styles.tabText, activeTab === t.key && styles.tabTextActive]}>{t.label}</Text>
                {(t.badge ?? 0) > 0 && (
                  <View style={amendStyles.tabBadge}>
                    <Text style={amendStyles.tabBadgeText}>{t.badge}</Text>
                  </View>
                )}
              </View>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* ── Members ─────────────────────────────────────────────────── */}
        {activeTab === 'members' && (
          <View style={styles.section}>
            {/* Pending join requests — compact entry row for admins */}
            {isAdmin && joinRequests.length > 0 && (
              <TouchableOpacity
                style={styles.joinRequestEntry}
                onPress={() => router.push({
                  pathname: "/contribution/[id]/join-requests",
                  params: { id: String(contributionId), title: contribution.title },
                })}
                activeOpacity={0.75}
              >
                <View style={styles.joinRequestEntryLeft}>
                  <View style={styles.joinRequestBadge}>
                    <Text style={styles.joinRequestBadgeText}>{joinRequests.length}</Text>
                  </View>
                  <View>
                    <Text style={styles.joinRequestEntryTitle}>
                      {joinRequests.length} join request{joinRequests.length !== 1 ? 's' : ''} pending
                    </Text>
                    <Text style={styles.joinRequestEntrySub}>Tap to review and approve</Text>
                  </View>
                </View>
                <Ionicons name="chevron-forward" size={16} color={COLORS.primary} />
              </TouchableOpacity>
            )}

            {participants.length === 0 ? (
              <Text style={styles.empty}>No members yet.</Text>
            ) : participants.map((p) => {
              // For the logged-in user, fall back to the name saved at login if server hasn't returned one yet
              const displayName   = p.name || (p.phone_number === myPhone ? myName : null) || null;
              const memberTarget  = contribution?.member_target_amount;
              const hasMemberGoal = !!memberTarget && p.progress_pct !== null;
              const pct           = Math.min(p.progress_pct ?? 0, 100);
              const reached       = pct >= 100;
              return (
                <View key={p.id} style={styles.memberRow}>
                  <Avatar name={displayName || p.phone_number || "?"} size={36} />
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={styles.memberName}>{displayName || p.phone_number}</Text>
                    {displayName && p.phone_number
                      ? <Text style={styles.memberPhone}>{p.phone_number}</Text>
                      : null}
                    {hasMemberGoal && (
                      <>
                        {/* Progress bar */}
                        <View style={styles.progressBarBg}>
                          <View style={[
                            styles.progressBarFill,
                            { width: `${pct}%` as any },
                            reached && { backgroundColor: COLORS.success },
                          ]} />
                        </View>
                        <Text style={[styles.progressBarLabel, reached && { color: COLORS.success }]}>
                          {reached
                            ? `✓ Goal reached — KES ${Number(p.balance).toLocaleString()}`
                            : `KES ${Number(p.balance).toLocaleString()} of KES ${Number(memberTarget).toLocaleString()} (${pct.toFixed(0)}%)`}
                        </Text>
                      </>
                    )}
                  </View>
                </View>
              );
            })}
          </View>
        )}

        {/* ── Activity ─────────────────────────────────────────────────── */}
        {activeTab === 'transactions' && (
          <View style={styles.section}>
            {transactions.length === 0 ? (
              <View style={styles.emptyBox}>
                <Ionicons name="receipt-outline" size={40} color={COLORS.textMuted} />
                <Text style={styles.emptyBoxTitle}>No activity yet</Text>
                <Text style={styles.emptyBoxSub}>M-Pesa payments and disbursements appear here.</Text>
              </View>
            ) : transactions.map((tx) => {
              const isCredit = tx.transaction_type === 'CONTRIBUTION' || tx.transaction_type === 'REPAYMENT';
              const color    = TX_COLOR[tx.transaction_type] ?? COLORS.textMuted;
              const label    = TX_LABEL[tx.transaction_type] ?? tx.transaction_type;
              const displayName = tx.name || tx.phone_number;
              return (
                <TouchableOpacity key={tx.id} style={styles.txRow} activeOpacity={0.7} onPress={() => setSelectedTx(tx)}>
                  {/* Colored icon circle */}
                  <View style={[styles.txIconWrap, { backgroundColor: color + '22' }]}>
                    <Ionicons
                      name={isCredit ? 'arrow-down-outline' : 'arrow-up-outline'}
                      size={16}
                      color={color}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.txType}>{label}</Text>
                    <Text style={styles.txNote} numberOfLines={1}>{displayName}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={[styles.txAmount, { color }]}>
                      {isCredit ? '+' : '-'} KES {Number(tx.amount).toLocaleString()}
                    </Text>
                    <Text style={styles.txDate}>{new Date(tx.created_at).toLocaleDateString('en-KE', { day: '2-digit', month: 'short' })}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textMuted} style={{ marginLeft: 4 }} />
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        {/* ── Disbursements ────────────────────────────────────────────── */}
        {activeTab === 'disbursements' && (
          <View style={styles.section}>

            {/* Standing Orders — summary entry point */}
            {isAdmin && (
              <>
                <TouchableOpacity
                  style={styles.soSummaryRow}
                  onPress={() => setShowManageOrders(true)}
                  activeOpacity={0.7}
                >
                  <View style={styles.soSummaryLeft}>
                    <Ionicons name="calendar-outline" size={20} color={COLORS.primary} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.sectionLabel}>STANDING ORDERS</Text>
                      <Text style={styles.soSummarySubtitle}>
                        {activeOrderCount > 0
                          ? `${activeOrderCount} active · tap to manage`
                          : 'None set up yet · tap to create'}
                      </Text>
                    </View>
                  </View>
                  <View style={styles.soSummaryRight}>
                    {activeOrderCount > 0 && (
                      <View style={styles.soBadge}>
                        <Text style={styles.soBadgeText}>{activeOrderCount}</Text>
                      </View>
                    )}
                    <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                  </View>
                </TouchableOpacity>
                <View style={styles.dividerLine} />
              </>
            )}

            {/* Disbursement Requests */}
            <View style={styles.sectionHead}>
              <Text style={styles.sectionLabel}>DISBURSEMENT REQUESTS</Text>
              <TouchableOpacity onPress={() => { if (requireKYC()) setShowDisbursement(true); }}>
                <Text style={styles.sectionAction}>+ Request</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.secNote}>
              Requires {contribution.voting_label} approval before funds move.
            </Text>
            {disbursements.length === 0 ? (
              <Text style={styles.empty}>No disbursement requests yet.</Text>
            ) : disbursements.map((d) => (
              <View key={d.id} style={styles.card}>
                <View style={styles.cardHead}>
                  <Text style={styles.cardAmount}>KES {Number(d.amount).toLocaleString()}</Text>
                  <View style={[styles.statusPill, statusBg(d.status)]}>
                    <Text style={styles.statusText}>{d.status}</Text>
                  </View>
                </View>
                <Text style={styles.cardNote}>{d.reason}</Text>
                <Text style={styles.cardMeta}>
                  {d.requested_by_phone} · {d.approve_count}/{d.required_approvals} approval{d.required_approvals !== 1 ? 's' : ''}
                </Text>
                {d.status === 'PENDING' && d.required_approvals > 0 && (
                  <View style={amendStyles.progressBg}>
                    <View style={[amendStyles.progressFill, {
                      width: `${Math.min((d.approve_count / d.required_approvals) * 100, 100)}%`,
                    }]} />
                  </View>
                )}
                {d.status === 'PENDING' && d.requested_by_phone !== myPhone && (
                  (() => {
                    const myVote = d.votes.find((v) => v.voter_phone === myPhone);
                    if (myVote) {
                      return (
                        <Text style={[styles.ownRequestNote, {
                          color: myVote.vote === 'APPROVE' ? COLORS.success : COLORS.error,
                        }]}>
                          You voted {myVote.vote.toLowerCase()}
                        </Text>
                      );
                    }
                    return (
                      <View style={styles.voteRow}>
                        <TouchableOpacity style={[styles.voteBtn, { backgroundColor: COLORS.success }]} onPress={() => voteDisbursement(d.id, 'APPROVE').then(load)}>
                          <Text style={styles.voteBtnText}>Approve</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={[styles.voteBtn, { backgroundColor: COLORS.error }]} onPress={() => voteDisbursement(d.id, 'REJECT').then(load)}>
                          <Text style={styles.voteBtnText}>Reject</Text>
                        </TouchableOpacity>
                      </View>
                    );
                  })()
                )}
                {d.status === 'PENDING' && d.requested_by_phone === myPhone && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 6 }}>
                    <Text style={styles.ownRequestNote}>Awaiting approval — you submitted this</Text>
                    <TouchableOpacity
                      onPress={() => handleCancelDisbursement(d.id)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.error }}
                    >
                      <Ionicons name="close-circle-outline" size={14} color={COLORS.error} />
                      <Text style={{ color: COLORS.error, fontSize: 12, fontWeight: '500' }}>Withdraw</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>
            ))}
          </View>
        )}

        {/* ── Amendments ──────────────────────────────────────────────── */}
        {activeTab === 'amendments' && (
          <View style={styles.section}>
            <View style={styles.sectionHead}>
              <Text style={styles.sectionLabel}>AMENDMENT PROPOSALS</Text>
              {isAdmin && (
                <TouchableOpacity onPress={handleAmendOpen}>
                  <Text style={styles.sectionAction}>+ Propose</Text>
                </TouchableOpacity>
              )}
            </View>
            <Text style={styles.secNote}>
              Changes to sensitive settings (amounts, thresholds, visibility) require group approval before taking effect.
            </Text>

            {amendments.length === 0 ? (
              <Text style={styles.empty}>No amendments proposed yet.</Text>
            ) : amendments.map((a) => {
              const myVote = a.votes.find((v) => v.voter_phone === myPhone);
              const canVote = a.status === 'PENDING' && a.proposed_by_phone !== myPhone && !myVote;
              return (
                <View key={a.id} style={[styles.card, a.status !== 'PENDING' && { opacity: 0.75 }]}>
                  <View style={styles.cardHead}>
                    <Text style={amendStyles.amendTitle}>
                      {a.changes_display.map((c) => c.field).join(', ')}
                    </Text>
                    <View style={[styles.statusPill, statusBg(a.status)]}>
                      <Text style={styles.statusText}>{a.status}</Text>
                    </View>
                  </View>

                  {/* Change details */}
                  {a.changes_display.map((c, i) => (
                    <View key={i} style={amendStyles.changeRow}>
                      <Text style={amendStyles.changeField}>{c.field}</Text>
                      <Text style={amendStyles.changeVal}>{c.from} → <Text style={{ color: COLORS.primary, fontWeight: '700' }}>{c.to}</Text></Text>
                    </View>
                  ))}

                  {a.reason ? <Text style={amendStyles.amendReason}>"{a.reason}"</Text> : null}

                  <Text style={styles.cardMeta}>
                    Proposed by {a.proposed_by_name} · {a.approve_count}/{a.required_approvals} approvals · {new Date(a.created_at).toLocaleDateString()}
                  </Text>

                  {/* Progress bar */}
                  {a.status === 'PENDING' && a.required_approvals > 0 && (
                    <View style={amendStyles.progressBg}>
                      <View style={[amendStyles.progressFill, { width: `${Math.min((a.approve_count / a.required_approvals) * 100, 100)}%` }]} />
                    </View>
                  )}

                  {canVote && (
                    <View style={styles.voteRow}>
                      <TouchableOpacity style={[styles.voteBtn, { backgroundColor: COLORS.success }]} onPress={() => handleVoteAmendment(a.id, 'APPROVE')}>
                        <Ionicons name="thumbs-up-outline" size={14} color={COLORS.white} />
                        <Text style={styles.voteBtnText}>Approve</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={[styles.voteBtn, { backgroundColor: COLORS.error }]} onPress={() => handleVoteAmendment(a.id, 'REJECT')}>
                        <Ionicons name="thumbs-down-outline" size={14} color={COLORS.white} />
                        <Text style={styles.voteBtnText}>Reject</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                  {a.status === 'PENDING' && a.proposed_by_phone === myPhone && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8 }}>
                      <Text style={styles.ownRequestNote}>You proposed this — awaiting group vote</Text>
                      <TouchableOpacity
                        onPress={() => handleWithdrawAmendment(a.id)}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.error }}
                      >
                        <Ionicons name="close-outline" size={14} color={COLORS.error} />
                        <Text style={{ fontSize: FONTS.sm, color: COLORS.error, fontWeight: '600' }}>Withdraw</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                  {a.status === 'WITHDRAWN' && (
                    <Text style={[styles.ownRequestNote, { color: COLORS.textMuted }]}>
                      {a.proposed_by_phone === myPhone ? 'You withdrew this proposal' : 'Proposal was withdrawn by the proposer'}
                    </Text>
                  )}
                  {a.status === 'PENDING' && myVote && (
                    <Text style={[styles.ownRequestNote, { color: myVote.vote === 'APPROVE' ? COLORS.success : COLORS.error }]}>
                      You voted {myVote.vote.toLowerCase()} · waiting for more votes
                    </Text>
                  )}
                </View>
              );
            })}
          </View>
        )}

      </ScrollView>

      {/* ── Modals ──────────────────────────────────────────────────────── */}

      {/* M-Pesa */}
      <Modal visible={showMpesa} transparent animationType="slide">
        <View style={styles.sheetOverlay}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Pay with M-Pesa</Text>
            <Text style={styles.sheetHint}>You'll receive an M-Pesa prompt. Enter your PIN to confirm.</Text>
            <Text style={styles.fieldLabel}>Amount (KES)</Text>
            <TextInput value={amount} onChangeText={setAmount} placeholder={contribution.fixed_amount ? `KES ${Number(contribution.fixed_amount).toLocaleString()}` : "e.g. 500"} placeholderTextColor={COLORS.textMuted} style={[styles.input, { fontSize: FONTS.xl, textAlign: "center" }]} keyboardType="numeric" autoFocus />
            <Text style={styles.fieldLabel}>Phone (optional)</Text>
            <TextInput value={mpesaPhone} onChangeText={setMpesaPhone} placeholder="07xxxxxxxx (defaults to yours)" placeholderTextColor={COLORS.textMuted} style={styles.input} keyboardType="phone-pad" />
            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowMpesa(false); setAmount(""); setMpesaPhone(""); }}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleMpesaPush} disabled={submitting}>
                {submitting ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.confirmText}>Send Prompt</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Disbursement */}
      <Modal visible={showDisbursement} transparent animationType="slide">
        <View style={styles.sheetOverlay}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Request Disbursement</Text>
            <Text style={styles.fieldLabel}>Amount (KES)</Text>
            <TextInput value={amount} onChangeText={setAmount} placeholder="e.g. 5000" placeholderTextColor={COLORS.textMuted} style={styles.input} keyboardType="numeric" />
            <Text style={styles.fieldLabel}>Reason</Text>
            <TextInput value={disbReason} onChangeText={setDisbReason} placeholder="Why do you need this?" placeholderTextColor={COLORS.textMuted} style={[styles.input, { height: 70, textAlignVertical: "top" }]} multiline />
            <Text style={styles.fieldLabel}>Recipient M-Pesa (optional)</Text>
            <TextInput value={disbRecipient} onChangeText={setDisbRecipient} placeholder="07xxxxxxxx" placeholderTextColor={COLORS.textMuted} style={styles.input} keyboardType="phone-pad" />
            <Text style={styles.sheetHint}>Requires {contribution.voting_label} to approve.</Text>
            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowDisbursement(false)}><Text style={styles.cancelText}>Cancel</Text></TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleCreateDisbursement} disabled={submitting}>
                {submitting ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.confirmText}>Submit</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Manage Standing Orders sheet */}
      <Modal visible={showManageOrders} transparent animationType="slide" onRequestClose={() => setShowManageOrders(false)}>
        <View style={styles.sheetOverlay}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setShowManageOrders(false)} />
          <View style={[styles.sheet, { maxHeight: '85%' }]}>
            <View style={styles.sheetHandle} />
            <View style={[styles.sectionHead, { marginBottom: 16 }]}>
              <Text style={styles.sheetTitle}>Standing Orders</Text>
              <TouchableOpacity
                style={styles.soNewBtn}
                onPress={() => { setShowManageOrders(false); setShowStandingOrder(true); }}
              >
                <Ionicons name="add" size={15} color={COLORS.white} />
                <Text style={styles.soNewBtnText}>New</Text>
              </TouchableOpacity>
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {standingOrders.length === 0 ? (
                <Text style={styles.empty}>No standing orders yet.</Text>
              ) : standingOrders.map((order) => {
                const totalSlots = order.slots.length;
                const doneSlots  = order.slots.filter((s) => s.has_received).length;
                const allDone    = order.payee_type === 'rotating' && totalSlots > 0 && doneSlots === totalSlots;
                return (
                  <View key={order.id} style={[styles.card, !order.is_active && { opacity: 0.55 }]}>
                    <View style={styles.cardHead}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.cardAmount}>KES {Number(order.amount).toLocaleString()}</Text>
                        <Text style={styles.cardMeta}>
                          {order.frequency.charAt(0).toUpperCase() + order.frequency.slice(1)}
                          {' · '}
                          {order.payee_type === 'fixed'
                            ? `Fixed → ${order.fixed_payee_phone}`
                            : `Rotating (${doneSlots}/${totalSlots} paid)`}
                        </Text>
                      </View>
                      <View style={[styles.statusPill, order.is_active ? { backgroundColor: COLORS.primaryPale } : { backgroundColor: COLORS.divider }]}>
                        <Text style={styles.statusText}>{order.is_active ? 'ACTIVE' : 'CANCELLED'}</Text>
                      </View>
                    </View>

                    {order.payee_type === 'rotating' && order.next_slot && (
                      <View style={styles.soNextRow}>
                        <Ionicons name="person-outline" size={14} color={COLORS.primary} />
                        <Text style={styles.soNextText}>
                          Next: {order.next_slot.name || order.next_slot.phone_number}
                        </Text>
                      </View>
                    )}

                    {order.payee_type === 'rotating' && allDone && (
                      <Text style={styles.soAllDone}>All members have received a payout.</Text>
                    )}

                    {order.is_active && !allDone && (
                      <View style={styles.voteRow}>
                        <TouchableOpacity
                          style={[styles.voteBtn, { backgroundColor: COLORS.primary }]}
                          onPress={() => handleExecuteOrder(order.id)}
                        >
                          <Text style={styles.voteBtnText}>Execute</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={[styles.voteBtn, { backgroundColor: COLORS.textSecondary }]}
                          onPress={() => { setShowManageOrders(false); handleOpenEditOrder(order); }}
                        >
                          <Ionicons name="pencil-outline" size={13} color={COLORS.white} />
                          <Text style={styles.voteBtnText}>Edit</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={[styles.voteBtn, { backgroundColor: COLORS.error }]}
                          onPress={() => handleCancelOrder(order.id)}
                        >
                          <Text style={styles.voteBtnText}>Cancel</Text>
                        </TouchableOpacity>
                      </View>
                    )}
                  </View>
                );
              })}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Standing Order create modal */}
      <Modal visible={showStandingOrder} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>New Standing Order</Text>

            <Text style={styles.fieldLabel}>Amount (KES)</Text>
            <TextInput
              style={styles.fieldInput}
              placeholder="e.g. 5000"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
              value={soAmount}
              onChangeText={setSoAmount}
            />

            <Text style={styles.fieldLabel}>Frequency</Text>
            <View style={{ flexDirection: "row", gap: 8, marginBottom: 14 }}>
              {(['daily','weekly','monthly'] as const).map((f) => (
                <TouchableOpacity
                  key={f}
                  style={[styles.chip, soFrequency === f && styles.chipActive]}
                  onPress={() => setSoFrequency(f)}
                >
                  <Text style={[styles.chipText, soFrequency === f && styles.chipTextActive]}>
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Payee</Text>
            <View style={{ flexDirection: "row", gap: 8, marginBottom: 14 }}>
              <TouchableOpacity
                style={[styles.optionPill, soPayeeType === 'fixed' && styles.optionPillActive]}
                onPress={() => setSoPayeeType('fixed')}
              >
                <Ionicons name="person-outline" size={14} color={soPayeeType === 'fixed' ? COLORS.white : COLORS.textMuted} />
                <Text style={[styles.optionPillText, soPayeeType === 'fixed' && styles.optionPillTextActive]}>Fixed Payee</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.optionPill, soPayeeType === 'rotating' && styles.optionPillActive]}
                onPress={() => setSoPayeeType('rotating')}
              >
                <Ionicons name="refresh-outline" size={14} color={soPayeeType === 'rotating' ? COLORS.white : COLORS.textMuted} />
                <Text style={[styles.optionPillText, soPayeeType === 'rotating' && styles.optionPillTextActive]}>Rotating</Text>
              </TouchableOpacity>
            </View>

            {soPayeeType === 'fixed' && (
              <>
                <Text style={styles.fieldLabel}>Payee Phone Number</Text>
                <TextInput
                  style={styles.fieldInput}
                  placeholder="+254700000000"
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="phone-pad"
                  value={soPhone}
                  onChangeText={setSoPhone}
                />
              </>
            )}

            {soPayeeType === 'rotating' && (
              <View style={styles.soHint}>
                <Ionicons name="information-circle-outline" size={16} color={COLORS.primary} />
                <Text style={styles.soHintText}>
                  Funds will be paid out to each active member in turn, one per execution.
                </Text>
              </View>
            )}

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancel}
                onPress={() => { setShowStandingOrder(false); setSoAmount(""); setSoPhone(""); }}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalConfirm} onPress={handleCreateStandingOrder} disabled={submitting}>
                {submitting ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.modalConfirmText}>Create</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Edit Standing Order modal */}
      <Modal visible={showEditOrder} transparent animationType="slide" onRequestClose={() => setShowEditOrder(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>Edit Standing Order</Text>

            <Text style={styles.fieldLabel}>Amount (KES)</Text>
            <TextInput
              style={styles.fieldInput}
              placeholder="e.g. 5000"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="numeric"
              value={editOrderAmount}
              onChangeText={setEditOrderAmount}
            />

            <Text style={styles.fieldLabel}>Frequency</Text>
            <View style={{ flexDirection: "row", gap: 8, marginBottom: 14 }}>
              {(['daily','weekly','monthly'] as const).map((f) => (
                <TouchableOpacity
                  key={f}
                  style={[styles.chip, editOrderFreq === f && styles.chipActive]}
                  onPress={() => setEditOrderFreq(f)}
                >
                  <Text style={[styles.chipText, editOrderFreq === f && styles.chipTextActive]}>
                    {f.charAt(0).toUpperCase() + f.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {editOrderPayeeType === 'fixed' && (
              <>
                <Text style={styles.fieldLabel}>Payee Phone Number</Text>
                <TextInput
                  style={styles.fieldInput}
                  placeholder="+254700000000"
                  placeholderTextColor={COLORS.textMuted}
                  keyboardType="phone-pad"
                  value={editOrderPhone}
                  onChangeText={setEditOrderPhone}
                />
              </>
            )}

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancel}
                onPress={() => setShowEditOrder(false)}
              >
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.modalConfirm} onPress={handleSaveEditOrder} disabled={editOrderSaving}>
                {editOrderSaving
                  ? <ActivityIndicator color={COLORS.white} />
                  : <Text style={styles.modalConfirmText}>Save Changes</Text>
                }
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Transaction Detail Sheet */}
      <Modal
        visible={!!selectedTx}
        transparent
        animationType="slide"
        onRequestClose={() => setSelectedTx(null)}
      >
        <View style={styles.sheetOverlay}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setSelectedTx(null)} />
          {selectedTx && (() => {
            const isCredit = selectedTx.transaction_type === 'CONTRIBUTION' || selectedTx.transaction_type === 'REPAYMENT';
            const color    = TX_COLOR[selectedTx.transaction_type] ?? COLORS.textMuted;
            const label    = TX_LABEL[selectedTx.transaction_type] ?? selectedTx.transaction_type;
            const dt       = new Date(selectedTx.created_at);
            const dateStr  = dt.toLocaleDateString('en-KE', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
            const timeStr  = dt.toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return (
              <View style={[styles.sheet, { paddingBottom: 32 }]}>
                {/* Header strip */}
                <View style={{ alignItems: 'center', marginBottom: 20 }}>
                  <View style={[styles.txIconWrap, { backgroundColor: color + '22', width: 52, height: 52, borderRadius: 26 }]}>
                    <Ionicons name={isCredit ? 'arrow-down-outline' : 'arrow-up-outline'} size={24} color={color} />
                  </View>
                  <Text style={{ fontSize: 26, fontWeight: '700', color: color, marginTop: 10 }}>
                    {isCredit ? '+' : '-'} KES {Number(selectedTx.amount).toLocaleString()}
                  </Text>
                  <Text style={{ fontSize: FONTS.md, color: COLORS.textSecondary, fontWeight: '500', marginTop: 2 }}>
                    {label}
                  </Text>
                </View>

                {/* Detail rows */}
                <View style={txDetailStyles.table}>
                  <TxDetailRow label="Date" value={dateStr} />
                  <TxDetailRow label="Time" value={timeStr} />
                  <TxDetailRow
                    label="By"
                    value={selectedTx.name
                      ? `${selectedTx.name} (${selectedTx.phone_number})`
                      : selectedTx.phone_number}
                  />
                  {selectedTx.note ? <TxDetailRow label="Note" value={selectedTx.note} /> : null}
                  <TxDetailRow label="Platform Ref" value={selectedTx.platform_ref} mono />
                  {selectedTx.mpesa_receipt
                    ? <TxDetailRow label="M-Pesa Ref" value={selectedTx.mpesa_receipt} mono highlight />
                    : <TxDetailRow label="M-Pesa Ref" value="—" />
                  }
                </View>

                <View style={{ flexDirection: 'row', gap: 10, marginTop: 24 }}>
                  {/* Download */}
                  <TouchableOpacity
                    style={[styles.modalCancel, { flex: 1, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 6, borderColor: COLORS.primary }]}
                    disabled={downloadingReceipt}
                    onPress={async () => {
                      if (!selectedTx || !contribution) return;
                      setDownloading(true);
                      await downloadReceipt(selectedTx, contribution.title);
                      setDownloading(false);
                    }}
                  >
                    {downloadingReceipt
                      ? <ActivityIndicator size="small" color={COLORS.primary} />
                      : <Ionicons name="download-outline" size={16} color={COLORS.primary} />
                    }
                    <Text style={[styles.modalCancelText, { color: COLORS.primary }]}>
                      {downloadingReceipt ? 'Generating…' : 'Download PDF'}
                    </Text>
                  </TouchableOpacity>

                  {/* Done */}
                  <TouchableOpacity
                    style={[styles.modalConfirm, { flex: 1 }]}
                    onPress={() => setSelectedTx(null)}
                  >
                    <Text style={styles.modalConfirmText}>Done</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })()}
        </View>
      </Modal>

      {/* Invite member modal */}
      <Modal visible={showInvite} transparent animationType="slide" onRequestClose={() => setShowInvite(false)}>
        <View style={styles.sheetOverlay}>
          <View style={styles.sheet}>
            <Text style={styles.sheetTitle}>Invite Member</Text>
            <Text style={styles.sheetHint}>
              The person must already be a member of this community. They'll receive a notification to accept or decline.
            </Text>
            <Text style={styles.fieldLabel}>Phone Number</Text>
            <TextInput
              style={styles.input}
              value={invitePhone}
              onChangeText={setInvitePhone}
              placeholder="+254700000000"
              placeholderTextColor={COLORS.textMuted}
              keyboardType="phone-pad"
              autoFocus
            />
            <View style={styles.sheetActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => { setShowInvite(false); setInvitePhone(""); }}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleInviteSend} disabled={inviteSending}>
                {inviteSending ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.confirmText}>Send Invite</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },

  pollingBanner: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: COLORS.primary, padding: 10, paddingHorizontal: 16 },
  pollingText:   { color: COLORS.white, fontSize: FONTS.sm, fontWeight: "600" },

  statusBanner:         { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#555", paddingVertical: 10, paddingHorizontal: 16 },
  statusBannerArchived: { backgroundColor: COLORS.textMuted },
  statusBannerText:     { color: COLORS.white, fontSize: FONTS.sm, fontWeight: "600", flex: 1 },

  hero:         { backgroundColor: COLORS.primary, padding: 24, paddingTop: 20 },
  heroAmount:   { fontSize: 36, fontWeight: "700", color: COLORS.white, marginBottom: 12 },
  progressBg:   { height: 6, backgroundColor: "rgba(255,255,255,0.3)", borderRadius: RADIUS.full, overflow: "hidden", marginBottom: 6 },
  progressFill: { height: "100%", backgroundColor: COLORS.white },
  progressLabel: { fontSize: FONTS.sm, color: "rgba(255,255,255,0.8)", marginBottom: 10 },
  heroBadges:   { flexDirection: "row", flexWrap: "wrap", gap: 6, marginBottom: 10 },
  heroBadge:    { paddingHorizontal: 8, paddingVertical: 3, backgroundColor: "rgba(255,255,255,0.2)", borderRadius: RADIUS.full },
  heroBadgeText: { fontSize: 11, fontWeight: "700", color: COLORS.white },
  heroMeta:     { fontSize: FONTS.sm, color: "rgba(255,255,255,0.75)" },

  joinRequestEntry: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.md,
    padding: 14, marginBottom: 12,
    borderWidth: 1, borderColor: COLORS.primary + "30",
  },
  joinRequestEntryLeft:  { flexDirection: "row", alignItems: "center", gap: 12 },
  joinRequestBadge:      { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.primary, justifyContent: "center", alignItems: "center" },
  joinRequestBadgeText:  { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },
  joinRequestEntryTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.primary },
  joinRequestEntrySub:   { fontSize: FONTS.sm, color: COLORS.textSecondary, marginTop: 1 },

  mpesaBtn:     { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: "#1D7A45", margin: 16, marginBottom: 8, padding: 15, borderRadius: RADIUS.md },
  mpesaBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },

  // Matches the mpesaBtn margin exactly so it sits in the same position
  requestJoinBtn:  { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, borderWidth: 2, borderColor: COLORS.primary, borderRadius: RADIUS.md, margin: 16, marginBottom: 8, padding: 15 },
  requestJoinText: { color: COLORS.primary, fontWeight: "700", fontSize: FONTS.md },

  requestPendingBanner: { flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "#fef7e0", borderRadius: RADIUS.md, marginHorizontal: 16, marginBottom: 4, paddingVertical: 12, paddingHorizontal: 14 },
  requestPendingText:   { flex: 1, fontSize: FONTS.sm, color: COLORS.accent, fontWeight: "600", lineHeight: 18 },

  inviteBanner:       { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: COLORS.primaryPale, borderRadius: RADIUS.md, marginHorizontal: 16, marginBottom: 4, paddingVertical: 14, paddingHorizontal: 14 },
  inviteBannerTitle:  { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.primary, marginBottom: 2 },
  inviteBannerSub:    { fontSize: FONTS.sm, color: COLORS.textSecondary, lineHeight: 18 },
  inviteAcceptBtn:    { backgroundColor: COLORS.primary, borderRadius: RADIUS.md, paddingHorizontal: 16, paddingVertical: 8, alignItems: "center" },
  inviteAcceptText:   { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },
  inviteDeclineBtn:   { borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md, paddingHorizontal: 16, paddingVertical: 8, alignItems: "center", marginTop: 4 },
  inviteDeclineText:  { color: COLORS.textSecondary, fontWeight: "600", fontSize: FONTS.sm },

  shareRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 16, paddingBottom: 12 },
  shareText: { fontSize: FONTS.sm, color: COLORS.textMuted },
  shareCode: { color: COLORS.primary, fontWeight: "700", fontFamily: "monospace" },

  tabScroll:     { paddingVertical: 12 },
  tab:           { paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: COLORS.white, borderWidth: 1, borderColor: COLORS.border },
  tabActive:     { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  tabText:       { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  tabTextActive: { color: COLORS.white },

  section:     { paddingHorizontal: 16, paddingBottom: 16 },
  sectionHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  sectionLabel: { fontSize: 11, fontWeight: "700", color: COLORS.textMuted, letterSpacing: 0.8 },
  sectionAction: { fontSize: FONTS.sm, fontWeight: "700", color: COLORS.primary },
  secNote:     { fontSize: FONTS.sm, color: COLORS.textSecondary, backgroundColor: COLORS.primaryPale, padding: 10, borderRadius: RADIUS.md, marginBottom: 12, lineHeight: 18 },
  empty:       { color: COLORS.textMuted, fontSize: FONTS.sm, fontStyle: "italic", marginTop: 8 },

  emptyBox:      { alignItems: "center", padding: 24, gap: 8 },
  emptyBoxTitle: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text },
  emptyBoxSub:   { fontSize: FONTS.sm, color: COLORS.textMuted, textAlign: "center", lineHeight: 20 },

  memberRow:   { flexDirection: "row", alignItems: "flex-start", paddingVertical: 8 },
  memberName:  { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text },
  memberPhone: { fontSize: FONTS.sm, color: COLORS.textMuted },
  progressBarBg: {
    height: 5, backgroundColor: COLORS.divider,
    borderRadius: 3, marginTop: 6, marginBottom: 3, overflow: "hidden",
  },
  progressBarFill: {
    height: "100%" as any, backgroundColor: COLORS.primary,
    borderRadius: 3,
  },
  progressBarLabel: {
    fontSize: 11, color: COLORS.textSecondary, fontWeight: "500",
  },

  txRow:      { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: COLORS.divider },
  txDot:      { width: 10, height: 10, borderRadius: 5 },
  txIconWrap: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  txType:     { fontSize: FONTS.sm, fontWeight: '700' as const, color: COLORS.text },
  txNote:     { fontSize: FONTS.xs, color: COLORS.textMuted },
  txDate:     { fontSize: 11, color: COLORS.textMuted },
  txAmount:   { fontSize: FONTS.sm, fontWeight: '700' as const },

  card:       { backgroundColor: COLORS.white, padding: 14, borderRadius: RADIUS.lg, marginBottom: 10, borderWidth: 1, borderColor: COLORS.border },
  cardHead:   { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  cardAmount: { fontSize: FONTS.lg, fontWeight: "700", color: COLORS.text },
  statusPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  statusText: { fontSize: 11, fontWeight: "700", color: COLORS.text },
  cardNote:   { fontSize: FONTS.sm, color: COLORS.textSecondary, marginBottom: 4 },
  cardMeta:       { fontSize: FONTS.sm, color: COLORS.textMuted },
  ownRequestNote: { fontSize: FONTS.sm, color: COLORS.textMuted, fontStyle: "italic", marginTop: 8 },
  voteRow:    { flexDirection: "row", gap: 8, marginTop: 10 },
  voteBtn:    { flex: 1, paddingVertical: 9, borderRadius: RADIUS.md, alignItems: "center" },
  voteBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.sm },

  menuOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.2)" },
  menuBox:     { position: "absolute", top: 90, right: 12, backgroundColor: COLORS.white, borderRadius: RADIUS.md, width: 220, shadowColor: "#000", shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.12, shadowRadius: 12, elevation: 8 },
  menuItem:    { flexDirection: "row", alignItems: "center", gap: 12, padding: 14 },
  menuItemText: { fontSize: FONTS.md, color: COLORS.text, fontWeight: "500" },
  menuDivider: { height: 1, backgroundColor: COLORS.divider },

  sheetOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  sheet:        { backgroundColor: COLORS.white, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40 },
  sheetHandle:  { width: 40, height: 4, backgroundColor: COLORS.border, borderRadius: 2, alignSelf: "center", marginBottom: 16 },
  sheetTitle:   { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginBottom: 8 },
  sheetHint:    { fontSize: FONTS.sm, color: COLORS.textMuted, marginBottom: 16, lineHeight: 18 },
  fieldLabel:   { fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary, marginBottom: 6, marginTop: 10 },
  input:        { borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md, padding: 13, fontSize: FONTS.md, color: COLORS.text, backgroundColor: COLORS.background, marginBottom: 4 },
  sheetActions: { flexDirection: "row", gap: 12, marginTop: 16 },
  cancelBtn:    { flex: 1, padding: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center" },
  cancelText:   { color: COLORS.textSecondary, fontWeight: "600" },
  confirmBtn:   { flex: 1, padding: 14, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  confirmText:  { color: COLORS.white, fontWeight: "700" },

  // Standing Orders — summary entry row
  soSummaryRow:      { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: COLORS.white, borderRadius: RADIUS.lg, padding: 14, borderWidth: 1, borderColor: COLORS.border, marginBottom: 12 },
  soSummaryLeft:     { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  soSummarySubtitle: { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 2 },
  soSummaryRight:    { flexDirection: "row", alignItems: "center", gap: 6 },
  soBadge:           { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2 },
  soBadgeText:       { fontSize: 11, fontWeight: "700" as const, color: COLORS.white },
  soNewBtn:          { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: COLORS.primary, paddingHorizontal: 12, paddingVertical: 7, borderRadius: RADIUS.md },
  soNewBtnText:      { fontSize: FONTS.sm, fontWeight: "700" as const, color: COLORS.white },

  // Standing Orders
  dividerLine:          { height: 1, backgroundColor: COLORS.divider, marginVertical: 20 },
  soNextRow:            { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 },
  soNextText:           { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "600" },
  soAllDone:            { fontSize: FONTS.sm, color: COLORS.success, fontWeight: "600", marginTop: 8 },
  optionPill:           { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.white },
  optionPillActive:     { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  optionPillText:       { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  optionPillTextActive: { color: COLORS.white },
  soHint:               { flexDirection: "row", alignItems: "flex-start", gap: 8, backgroundColor: COLORS.primaryPale, padding: 12, borderRadius: RADIUS.md, marginBottom: 14 },
  soHintText:           { flex: 1, fontSize: FONTS.sm, color: COLORS.primary, lineHeight: 18 },

  // Standing Order modal
  modalOverlay:      { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalSheet:        { backgroundColor: COLORS.white, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, paddingBottom: 40 },
  modalTitle:        { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.text, marginBottom: 8 },
  fieldInput:        { borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md, padding: 13, fontSize: FONTS.md, color: COLORS.text, backgroundColor: COLORS.background, marginBottom: 4 },
  chip:              { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.white },
  chipActive:        { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText:          { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  chipTextActive:    { color: COLORS.white },
  modalActions:      { flexDirection: "row", gap: 12, marginTop: 16 },
  modalCancel:       { flex: 1, padding: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center" },
  modalCancelText:   { color: COLORS.textSecondary, fontWeight: "600" },
  modalConfirm:      { flex: 1, padding: 14, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  modalConfirmText:  { color: COLORS.white, fontWeight: "700" },
});

const editStyles = StyleSheet.create({
  fieldLabel: {
    fontSize: FONTS.sm, fontWeight: "600", color: COLORS.textSecondary,
    marginBottom: 6, marginTop: 8,
  },
  input: {
    borderWidth: 1.5, borderColor: COLORS.border, borderRadius: RADIUS.md,
    padding: 13, fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background, marginBottom: 4,
  },
  segRow:      { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 4 },
  seg:         { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1.5, borderColor: COLORS.border, backgroundColor: COLORS.white },
  segActive:   { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  segText:     { fontSize: FONTS.sm, color: COLORS.textMuted, fontWeight: "600" },
  segTextActive: { color: COLORS.white },
  saveBtn:     { marginTop: 20, padding: 15, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: "center" },
  saveBtnText: { color: COLORS.white, fontWeight: "700", fontSize: FONTS.md },
  cancelBtn:   { marginTop: 10, padding: 14, borderRadius: RADIUS.md, borderWidth: 1.5, borderColor: COLORS.border, alignItems: "center", marginBottom: 8 },
  cancelBtnText: { color: COLORS.textSecondary, fontWeight: "600" },
});

const amendStyles = StyleSheet.create({
  tabBadge:     { minWidth: 18, height: 18, borderRadius: 9, backgroundColor: COLORS.primary, justifyContent: "center", alignItems: "center", paddingHorizontal: 4 },
  tabBadgeText: { fontSize: 10, fontWeight: "700", color: COLORS.white },
  amendTitle:   { fontSize: FONTS.md, fontWeight: "700", color: COLORS.text, flex: 1 },
  changeRow:    { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginVertical: 3 },
  changeField:  { fontSize: FONTS.sm, color: COLORS.textMuted, flex: 1 },
  changeVal:    { fontSize: FONTS.sm, color: COLORS.text, flex: 2, textAlign: "right" },
  amendReason:  { fontSize: FONTS.sm, color: COLORS.textSecondary, fontStyle: "italic", marginVertical: 6 },
  progressBg:   { height: 4, backgroundColor: COLORS.border, borderRadius: 2, marginTop: 8 },
  progressFill: { height: 4, backgroundColor: COLORS.primary, borderRadius: 2 },
});
