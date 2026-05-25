import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  View,
  Text,
  FlatList,
  TextInput,
  TouchableOpacity,
  TouchableWithoutFeedback,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Alert,
  Image,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import AsyncStorage from "@react-native-async-storage/async-storage"; // used for non-sensitive UI timestamps
import * as storage from "../../utils/secureStorage";
import { useLocalSearchParams, router } from "expo-router";
import * as ImagePicker from "expo-image-picker";
import * as Clipboard from "expo-clipboard";
import { useAudioPlayer, useAudioRecorder, AudioModule, RecordingPresets } from "expo-audio";
import EmojiKeyboard from "rn-emoji-keyboard";
import {
  getMessages, deleteMessage, bulkDeleteMessages, deleteConversation, editMessage,
  reactToMessage, sendVoiceMessage, markConversationRead, sendMessage,
  Message, ReplyTo,
} from "../../api/conversations";
import { emit } from "../../utils/eventBus";
import { COLORS, FONTS, RADIUS } from "../../constants/theme";
import { WS_BASE_URL } from "../../constants/config";
import AppHeader from "../../components/app/AppHeader";
import Avatar from "../../components/app/Avatar";

const QUICK_REACTIONS = ["❤️", "👍", "😂", "😮", "😢", "🙏"];

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch { return ""; }
}

function formatDuration(secs: number) {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function ReplyQuote({ rt, isMe }: { rt: ReplyTo; isMe: boolean }) {
  return (
    <View style={[styles.replyQuote, isMe ? styles.replyQuoteMe : styles.replyQuoteThem]}>
      <Text style={[styles.replyQuoteSender, isMe && { color: "rgba(255,255,255,0.8)" }]} numberOfLines={1}>
        {rt.deleted ? "Deleted message" : rt.sender}
      </Text>
      {!rt.deleted && (
        <Text style={[styles.replyQuoteContent, isMe && { color: "rgba(255,255,255,0.7)" }]} numberOfLines={2}>
          {rt.message_type === "image" ? "📷 Photo"
            : rt.message_type === "voice" ? "🎤 Voice message"
            : rt.message_type === "video" ? "🎥 Video"
            : rt.content}
        </Text>
      )}
    </View>
  );
}

function VoiceMessageBubble({ uri, isMe }: { uri: string; isMe: boolean }) {
  const player = useAudioPlayer({ uri });
  const iconColor = isMe ? "rgba(255,255,255,0.9)" : COLORS.primary;
  const barColor = isMe ? "rgba(255,255,255,0.6)" : COLORS.primary;

  return (
    <TouchableOpacity
      style={styles.voiceBubble}
      onPress={() => (player.playing ? player.pause() : player.play())}
    >
      <Ionicons name={player.playing ? "pause-circle" : "play-circle"} size={38} color={iconColor} />
      <View style={styles.voiceWave}>
        {[3, 6, 10, 14, 9, 12, 7, 11, 5, 8, 4].map((h, i) => (
          <View key={i} style={[styles.voiceBar, { height: h * 1.5, backgroundColor: barColor, opacity: player.playing ? 1 : 0.6 }]} />
        ))}
      </View>
    </TouchableOpacity>
  );
}

export default function ConversationScreen() {
  const { id, topic, communityId, createdBy, myRole } = useLocalSearchParams<{
    id: string; topic?: string; communityId?: string; createdBy?: string; myRole?: string;
  }>();
  const conversationId = Number(id);
  const insets = useSafeAreaInsets();

  const [messages, setMessages] = useState<Message[]>([]);
  const [myPhone, setMyPhone] = useState("");
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const [selectedMsg, setSelectedMsg] = useState<Message | null>(null);
  const [msgMenuVisible, setMsgMenuVisible] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [pendingMediaType, setPendingMediaType] = useState<"image" | "video">("image");
  const [sending, setSending] = useState(false);
  const [unreadFromIndex, setUnreadFromIndex] = useState(-1);
  const [replyingTo, setReplyingTo] = useState<Message | null>(null);
  const [editingMsg, setEditingMsg] = useState<Message | null>(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [typingUsers, setTypingUsers] = useState<string[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  const ws = useRef<WebSocket | null>(null);
  const flatRef = useRef<FlatList>(null);
  const recordingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const typingTimersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const lastTypingSentRef = useRef(0);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => flatRef.current?.scrollToEnd({ animated: true }), 100);
  }, []);

  // ── Setup: load messages + open WebSocket ────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const setup = async () => {
      const [token, phone] = await Promise.all([
        storage.getItem("access"),
        storage.getItem("phone"),
      ]);
      if (phone && !cancelled) setMyPhone(phone);

      const clearKey = phone ? `conv_cleared_${phone}_${conversationId}` : null;
      const visitKey = phone ? `conv_last_visit_${phone}_${conversationId}` : null;

      try {
        const [history, clearedAt, lastVisitAt] = await Promise.all([
          getMessages(conversationId),
          clearKey ? AsyncStorage.getItem(clearKey) : Promise.resolve(null),
          visitKey ? AsyncStorage.getItem(visitKey) : Promise.resolve(null),
        ]);

        if (!cancelled) {
          const visible = clearedAt
            ? history.filter((m) => new Date(m.created_at) > new Date(clearedAt))
            : history;
          setMessages(visible);

          if (lastVisitAt && visible.length > 0) {
            const divIdx = visible.findIndex(
              (m) => new Date(m.created_at) > new Date(lastVisitAt) && m.sender_phone !== phone
            );
            if (divIdx > 0) setUnreadFromIndex(divIdx);
          }
        }
      } catch {}

      if (visitKey) await AsyncStorage.setItem(visitKey, new Date().toISOString());
      if (!cancelled) {
        setLoading(false);
        markConversationRead(conversationId).catch(() => {});
      }

      const url = `${WS_BASE_URL}/ws/conversation/${conversationId}/?token=${token}`;
      ws.current = new WebSocket(url);
      ws.current.onopen = () => setConnected(true);
      ws.current.onclose = () => setConnected(false);
      ws.current.onerror = () => setConnected(false);

      ws.current.onmessage = (e) => {
        try {
          const d = JSON.parse(e.data);

          // ── Typing indicator ──────────────────────────────────────────────
          if (d.type === "typing") {
            if (d.sender_phone === phone) return;
            const name: string = d.sender;
            setTypingUsers((prev) => prev.includes(name) ? prev : [...prev, name]);
            if (typingTimersRef.current[d.sender_phone]) {
              clearTimeout(typingTimersRef.current[d.sender_phone]);
            }
            typingTimersRef.current[d.sender_phone] = setTimeout(() => {
              setTypingUsers((prev) => prev.filter((s) => s !== name));
            }, 3000);
            return;
          }

          // ── Message edited ────────────────────────────────────────────────
          if (d.type === "message_edited") {
            setMessages((prev) =>
              prev.map((m) => m.id === d.id ? { ...m, content: d.content, is_edited: true } : m)
            );
            return;
          }

          // ── Message deleted ───────────────────────────────────────────────
          if (d.type === "message_deleted") {
            setMessages((prev) => prev.filter((m) => m.id !== d.id));
            return;
          }

          // ── Reaction ──────────────────────────────────────────────────────
          if (d.type === "reaction") {
            setMessages((prev) => prev.map((m) => {
              if (m.id !== d.message_id) return m;
              const reactions = { ...m.reactions };
              // remove user from all emojis first
              for (const emoji of Object.keys(reactions)) {
                reactions[emoji] = reactions[emoji].filter((p) => p !== d.sender_phone);
                if (reactions[emoji].length === 0) delete reactions[emoji];
              }
              if (d.action !== "remove") {
                reactions[d.emoji] = [...(reactions[d.emoji] ?? []), d.sender_phone];
              }
              return { ...m, reactions };
            }));
            return;
          }

          // ── New message ───────────────────────────────────────────────────
          setMessages((prev) => [...prev, {
            id: d.id ?? Date.now(),
            sender: d.sender,
            sender_phone: d.sender_phone,
            content: d.message ?? "",
            message_type: d.message_type ?? "text",
            attachment: d.attachment ?? null,
            reply_to: d.reply_to ?? null,
            reactions: d.reactions ?? {},
            is_edited: false,
            created_at: d.created_at,
          }]);
          scrollToBottom();
          setUnreadFromIndex(-1);
          markConversationRead(conversationId).catch(() => {});
          emit("newMessage");
        } catch {}
      };
    };

    setup();
    return () => {
      cancelled = true;
      ws.current?.close();
    };
  }, [conversationId]);

  // ── Typing: send event on text change ────────────────────────────────────
  const handleTextChange = (t: string) => {
    setText(t);
    if (t.length > 0 && ws.current?.readyState === WebSocket.OPEN) {
      const now = Date.now();
      if (now - lastTypingSentRef.current > 2000) {
        ws.current.send(JSON.stringify({ type: "typing" }));
        lastTypingSentRef.current = now;
      }
    }
  };

  // ── Voice recording ───────────────────────────────────────────────────────
  const startRecording = async () => {
    try {
      const { granted } = await AudioModule.requestRecordingPermissionsAsync();
      if (!granted) { Alert.alert("Permission required", "Microphone access is needed."); return; }
      await recorder.record();
      setIsRecording(true);
      let secs = 0;
      recordingTimerRef.current = setInterval(() => { secs++; setRecordingDuration(secs); }, 1000);
    } catch { Alert.alert("Error", "Could not start recording."); }
  };

  const stopAndSendRecording = async () => {
    if (!isRecording) return;
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    setIsRecording(false);
    setRecordingDuration(0);
    setSending(true);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) return;
      await sendVoiceMessage(conversationId, uri, replyingTo?.id);
      setReplyingTo(null);
      scrollToBottom();
    } catch { Alert.alert("Error", "Failed to send voice message."); }
    finally { setSending(false); }
  };

  const cancelRecording = async () => {
    if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    setIsRecording(false);
    setRecordingDuration(0);
    await recorder.stop().catch(() => {});
  };

  // ── Send / Edit ───────────────────────────────────────────────────────────
  const send = async () => {
    if (sending) return;

    // Edit mode
    if (editingMsg) {
      const t = text.trim();
      if (!t) return;
      try {
        await editMessage(editingMsg.id, t);
        setMessages((prev) =>
          prev.map((m) => m.id === editingMsg!.id ? { ...m, content: t, is_edited: true } : m)
        );
        setEditingMsg(null);
        setText("");
      } catch { Alert.alert("Error", "Failed to edit message."); }
      return;
    }

    // Image / video via REST
    if (pendingImage) {
      setSending(true);
      try {
        await sendMessage(conversationId, text.trim(), pendingImage, replyingTo?.id, pendingMediaType);
        setPendingImage(null);
        setPendingMediaType("image");
        setText("");
        setReplyingTo(null);
        scrollToBottom();
      } catch { Alert.alert("Error", "Failed to send."); }
      finally { setSending(false); }
      return;
    }

    // Text via WebSocket
    const t = text.trim();
    if (!t || !ws.current || ws.current.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ message: t, reply_to_id: replyingTo?.id ?? null }));
    setText("");
    setReplyingTo(null);
  };

  // ── Media picker ──────────────────────────────────────────────────────────
  const pickMedia = async (source: "gallery" | "camera", mediaTypes: "images" | "videos") => {
    const picker = source === "camera" ? ImagePicker.launchCameraAsync : ImagePicker.launchImageLibraryAsync;
    const result = await picker({ mediaTypes, quality: 0.85, allowsEditing: false, videoMaxDuration: 60 } as any);
    if (!result.canceled && result.assets[0]) {
      setPendingImage(result.assets[0].uri);
      setPendingMediaType(mediaTypes === "videos" ? "video" : "image");
      setEmojiOpen(false);
    }
  };

  const showAttachmentSheet = () => {
    Alert.alert("Send Media", "Choose source", [
      { text: "📷  Camera – Photo", onPress: () => pickMedia("camera", "images") },
      { text: "🎥  Camera – Video", onPress: () => pickMedia("camera", "videos") },
      { text: "🖼  Gallery – Photo", onPress: () => pickMedia("gallery", "images") },
      { text: "🎬  Gallery – Video", onPress: () => pickMedia("gallery", "videos") },
      { text: "Cancel", style: "cancel" },
    ]);
  };

  // ── Conversation menu handlers ────────────────────────────────────────────
  const handleDeleteConversation = () => {
    setMenuVisible(false);
    Alert.alert("Delete Conversation", "This will permanently delete this conversation.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await deleteConversation(conversationId); router.back(); }
        catch (e: any) { Alert.alert("Error", e?.response?.data?.error || "Failed."); }
      }},
    ]);
  };

  const handleClearChat = () => {
    setMenuVisible(false);
    Alert.alert("Clear Chat", "Clears messages from your view only.", [
      { text: "Cancel", style: "cancel" },
      { text: "Clear", style: "destructive", onPress: async () => {
        const clearKey = `conv_cleared_${myPhone}_${conversationId}`;
        await AsyncStorage.setItem(clearKey, new Date().toISOString());
        setMessages([]);
      }},
    ]);
  };

  // ── Message long-press menu handlers ─────────────────────────────────────
  const isAdmin = myRole === 'admin' || createdBy === myPhone;

  const handleLongPress = (msg: Message) => {
    if (selectMode) {
      toggleSelect(msg.id);
      return;
    }
    setSelectedMsg(msg);
    setMsgMenuVisible(true);
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const enterSelectMode = (msg: Message) => {
    setMsgMenuVisible(false);
    setSelectMode(true);
    setSelectedIds(new Set([msg.id]));
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };

  const handleBulkDelete = () => {
    if (selectedIds.size === 0) return;
    Alert.alert(
      `Delete ${selectedIds.size} message${selectedIds.size > 1 ? 's' : ''}?`,
      'This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete', style: 'destructive',
          onPress: async () => {
            try {
              const deleted = await bulkDeleteMessages(conversationId, [...selectedIds]);
              setMessages((prev) => prev.filter((m) => !deleted.includes(m.id)));
            } catch {
              Alert.alert('Error', 'Failed to delete some messages.');
            } finally {
              exitSelectMode();
            }
          },
        },
      ]
    );
  };

  const handleReplyToMessage = () => {
    if (!selectedMsg) return;
    setMsgMenuVisible(false);
    setReplyingTo(selectedMsg);
    setEditingMsg(null);
    setEmojiOpen(false);
  };

  const handleEditMessage = () => {
    if (!selectedMsg || selectedMsg.message_type !== "text") return;
    setMsgMenuVisible(false);
    setEditingMsg(selectedMsg);
    setText(selectedMsg.content);
    setReplyingTo(null);
  };

  const handleCopyMessage = () => {
    if (!selectedMsg?.content) return;
    setMsgMenuVisible(false);
    Clipboard.setStringAsync(selectedMsg.content);
  };

  const handleReact = async (emoji: string) => {
    if (!selectedMsg) return;
    setMsgMenuVisible(false);
    try { await reactToMessage(selectedMsg.id, emoji); } catch {}
  };

  const handleReactInline = async (msgId: number, emoji: string) => {
    try { await reactToMessage(msgId, emoji); } catch {}
  };

  const handleDeleteMessage = async () => {
    if (!selectedMsg) return;
    setMsgMenuVisible(false);
    try {
      await deleteMessage(selectedMsg.id);
      setMessages((prev) => prev.filter((m) => m.id !== selectedMsg.id));
    } catch (e: any) {
      Alert.alert("Error", e?.response?.data?.error || "Failed to delete message.");
    }
  };

  const canDeleteSelected = (msg: Message) =>
    msg.sender_phone === myPhone || isAdmin;

  // ── List data with divider ────────────────────────────────────────────────
  type ListItem = Message | { type: "divider" };
  const listData = useMemo<ListItem[]>(() => {
    if (unreadFromIndex < 0) return messages;
    return [...messages.slice(0, unreadFromIndex), { type: "divider" }, ...messages.slice(unreadFromIndex)];
  }, [messages, unreadFromIndex]);

  const canSend = !sending && (!!editingMsg ? !!text.trim() : (!!text.trim() || !!pendingImage));
  const canRecord = !sending && !text.trim() && !pendingImage && !editingMsg;

  // ── Render helpers ────────────────────────────────────────────────────────
  const renderReactions = (item: Message, isMe: boolean) => {
    const entries = Object.entries(item.reactions ?? {}).filter(([, phones]) => phones.length > 0);
    if (!entries.length) return null;
    return (
      <View style={[styles.reactionsRow, isMe && styles.reactionsRowMe]}>
        {entries.map(([emoji, phones]) => (
          <TouchableOpacity
            key={emoji}
            style={[styles.reactionChip, phones.includes(myPhone) && styles.reactionChipMine]}
            onPress={() => handleReactInline(item.id, emoji)}
          >
            <Text style={styles.reactionEmoji}>{emoji}</Text>
            {phones.length > 1 && <Text style={styles.reactionCount}>{phones.length}</Text>}
          </TouchableOpacity>
        ))}
      </View>
    );
  };

  const renderItem = ({ item, index }: { item: ListItem; index: number }) => {
    if ("type" in item && item.type === "divider") {
      return (
        <View style={styles.unreadDivider}>
          <View style={styles.unreadDividerLine} />
          <Text style={styles.unreadDividerLabel}>New messages</Text>
          <View style={styles.unreadDividerLine} />
        </View>
      );
    }
    const msg = item as Message;
    const isMe = !!(myPhone && (msg.sender_phone === myPhone || (!msg.sender_phone && msg.sender === myPhone)));
    const msgIndex = messages.findIndex((m) => m.id === msg.id);
    const prev = msgIndex > 0 ? messages[msgIndex - 1] : null;
    const isFirstInGroup = !prev || (prev.sender_phone ?? prev.sender) !== (msg.sender_phone ?? msg.sender);
    const isImage = msg.message_type === "image" && !!msg.attachment;
    const isVoice = msg.message_type === "voice" && !!msg.attachment;
    const isVideo = msg.message_type === "video";
    const isSelected = selectedIds.has(msg.id);

    const bubbleContent = (forIsMe: boolean) => (
      <>
        {msg.reply_to && <ReplyQuote rt={msg.reply_to} isMe={forIsMe} />}
        {isVoice && <VoiceMessageBubble uri={msg.attachment!} isMe={forIsMe} />}
        {isImage && <Image source={{ uri: msg.attachment! }} style={styles.msgImage} resizeMode="cover" />}
        {isVideo && (
          <View style={[styles.videoPlaceholder, !forIsMe && { backgroundColor: COLORS.primaryBg }]}>
            <Ionicons name="videocam" size={32} color={forIsMe ? "rgba(255,255,255,0.9)" : COLORS.primary} />
            <Text style={{ color: forIsMe ? "rgba(255,255,255,0.8)" : COLORS.primary, fontSize: 12, marginTop: 4 }}>Video</Text>
          </View>
        )}
        {!!msg.content && <Text style={forIsMe ? styles.textMe : styles.textThem}>{msg.content}</Text>}
        <View style={styles.metaRow}>
          {msg.is_edited && <Text style={[styles.editedLabel, !forIsMe && { color: COLORS.textMuted }]}>edited</Text>}
          <Text style={forIsMe ? styles.timeMe : styles.timeThem}>{formatTime(msg.created_at)}</Text>
        </View>
      </>
    );

    if (isMe) {
      return (
        <View style={[styles.selectableRow, isSelected && styles.selectedRow]}>
          {selectMode && (
            <TouchableOpacity onPress={() => toggleSelect(msg.id)} style={styles.selectCircleWrap}>
              <View style={[styles.selectCircle, isSelected && styles.selectCircleActive]}>
                {isSelected && <Ionicons name="checkmark" size={14} color={COLORS.white} />}
              </View>
            </TouchableOpacity>
          )}
          <TouchableWithoutFeedback
            onPress={selectMode ? () => toggleSelect(msg.id) : undefined}
            onLongPress={() => handleLongPress(msg)}
          >
            <View style={styles.rowMe}>
              <View style={[styles.bubbleMe, (isImage || isVideo) && styles.bubbleImage]}>
                {bubbleContent(true)}
              </View>
            </View>
          </TouchableWithoutFeedback>
          {renderReactions(msg, true)}
        </View>
      );
    }

    return (
      <View style={[styles.selectableRow, isSelected && styles.selectedRow]}>
        {selectMode && (
          <TouchableOpacity onPress={() => toggleSelect(msg.id)} style={styles.selectCircleWrap}>
            <View style={[styles.selectCircle, isSelected && styles.selectCircleActive]}>
              {isSelected && <Ionicons name="checkmark" size={14} color={COLORS.white} />}
            </View>
          </TouchableOpacity>
        )}
        <TouchableWithoutFeedback
          onPress={selectMode ? () => toggleSelect(msg.id) : undefined}
          onLongPress={() => handleLongPress(msg)}
        >
          <View style={styles.rowThem}>
            {isFirstInGroup ? <Avatar name={msg.sender} size={32} /> : <View style={{ width: 32 }} />}
            <View style={{ flex: 1, maxWidth: "78%" }}>
              {isFirstInGroup && <Text style={styles.senderName}>{msg.sender}</Text>}
              <View style={[styles.bubbleThem, (isImage || isVideo) && styles.bubbleImage]}>
                {bubbleContent(false)}
              </View>
            </View>
          </View>
        </TouchableWithoutFeedback>
        {renderReactions(msg, false)}
      </View>
    );
  };

  // ── JSX ───────────────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <KeyboardAvoidingView style={styles.flex} behavior="padding" keyboardVerticalOffset={Platform.OS === "android" ? 24 : 0}>
        {selectMode ? (
          <View style={styles.selectionHeader}>
            <TouchableOpacity onPress={exitSelectMode} style={styles.selectionHeaderBtn}>
              <Ionicons name="close" size={24} color={COLORS.white} />
            </TouchableOpacity>
            <Text style={styles.selectionCount}>
              {selectedIds.size} selected
            </Text>
            <TouchableOpacity
              onPress={handleBulkDelete}
              style={[styles.selectionHeaderBtn, selectedIds.size === 0 && { opacity: 0.4 }]}
              disabled={selectedIds.size === 0}
            >
              <Ionicons name="trash-outline" size={22} color={COLORS.white} />
            </TouchableOpacity>
          </View>
        ) : (
          <AppHeader
            title={`${topic ?? "Conversation"}${connected ? " · online" : ""}`}
            variant="green"
            leading="back"
            rightIcon="more"
            onRightPress={() => setMenuVisible(true)}
          />
        )}

        {/* Conversation 3-dots menu */}
        <Modal visible={menuVisible} transparent animationType="fade" onRequestClose={() => setMenuVisible(false)}>
          <TouchableOpacity style={styles.menuOverlay} activeOpacity={1} onPress={() => setMenuVisible(false)}>
            <View style={styles.menuCard}>
              {(createdBy === myPhone || myRole === "admin") && (
                <>
                  <TouchableOpacity style={styles.menuItem} onPress={handleDeleteConversation}>
                    <Ionicons name="trash-outline" size={20} color={COLORS.error} />
                    <Text style={[styles.menuItemText, { color: COLORS.error }]}>Delete Conversation</Text>
                  </TouchableOpacity>
                  <View style={styles.menuDivider} />
                </>
              )}
              <TouchableOpacity style={styles.menuItem} onPress={handleClearChat}>
                <Ionicons name="close-circle-outline" size={20} color={COLORS.text} />
                <Text style={styles.menuItemText}>Clear Chat</Text>
              </TouchableOpacity>
            </View>
          </TouchableOpacity>
        </Modal>

        {/* Message long-press menu */}
        <Modal visible={msgMenuVisible} transparent animationType="fade" onRequestClose={() => setMsgMenuVisible(false)}>
          <TouchableOpacity style={styles.msgMenuOverlay} activeOpacity={1} onPress={() => setMsgMenuVisible(false)}>
            <View style={styles.msgMenuCard}>
              {/* Quick reactions */}
              <View style={styles.quickReactions}>
                {QUICK_REACTIONS.map((emoji) => (
                  <TouchableOpacity key={emoji} style={styles.quickReactionBtn} onPress={() => handleReact(emoji)}>
                    <Text style={styles.quickReactionEmoji}>{emoji}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <View style={styles.menuDivider} />

              {/* Reply */}
              <TouchableOpacity style={styles.menuItem} onPress={handleReplyToMessage}>
                <Ionicons name="return-down-back-outline" size={20} color={COLORS.primary} />
                <Text style={[styles.menuItemText, { color: COLORS.primary }]}>Reply</Text>
              </TouchableOpacity>

              {/* Copy (text messages only) */}
              {selectedMsg?.content ? (
                <>
                  <View style={styles.menuDivider} />
                  <TouchableOpacity style={styles.menuItem} onPress={handleCopyMessage}>
                    <Ionicons name="copy-outline" size={20} color={COLORS.text} />
                    <Text style={styles.menuItemText}>Copy</Text>
                  </TouchableOpacity>
                </>
              ) : null}

              {/* Select multiple */}
              <View style={styles.menuDivider} />
              <TouchableOpacity style={styles.menuItem} onPress={() => selectedMsg && enterSelectMode(selectedMsg)}>
                <Ionicons name="checkmark-circle-outline" size={20} color={COLORS.text} />
                <Text style={styles.menuItemText}>Select</Text>
              </TouchableOpacity>

              {/* Edit (own text messages only) */}
              {selectedMsg?.sender_phone === myPhone && selectedMsg.message_type === "text" && (
                <>
                  <View style={styles.menuDivider} />
                  <TouchableOpacity style={styles.menuItem} onPress={handleEditMessage}>
                    <Ionicons name="create-outline" size={20} color={COLORS.text} />
                    <Text style={styles.menuItemText}>Edit</Text>
                  </TouchableOpacity>
                </>
              )}

              {/* Delete — own messages or admin */}
              {selectedMsg && canDeleteSelected(selectedMsg) && (
                <>
                  <View style={styles.menuDivider} />
                  <TouchableOpacity style={styles.menuItem} onPress={handleDeleteMessage}>
                    <Ionicons name="trash-outline" size={20} color={COLORS.error} />
                    <Text style={[styles.menuItemText, { color: COLORS.error }]}>Delete</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          </TouchableOpacity>
        </Modal>

        {loading ? (
          <View style={styles.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
        ) : (
          <FlatList
            ref={flatRef}
            data={listData}
            keyExtractor={(item, i) => ("type" in item ? "divider" : String((item as Message).id ?? i))}
            renderItem={renderItem}
            contentContainerStyle={styles.list}
            onScrollToIndexFailed={() => scrollToBottom()}
            onContentSizeChange={() => {
              if (unreadFromIndex > 0) {
                setTimeout(() => flatRef.current?.scrollToIndex({ index: unreadFromIndex, animated: false, viewPosition: 0 }), 120);
              } else {
                scrollToBottom();
              }
            }}
            ListEmptyComponent={
              <View style={styles.center}>
                <Text style={styles.emptyText}>No messages yet.{"\n"}Say hello!</Text>
              </View>
            }
          />
        )}

        {/* Typing indicator */}
        {typingUsers.length > 0 && (
          <View style={styles.typingBar}>
            <Text style={styles.typingText}>
              {typingUsers.length === 1
                ? `${typingUsers[0]} is typing…`
                : `${typingUsers.slice(0, 2).join(", ")} are typing…`}
            </Text>
          </View>
        )}

        {/* Edit bar */}
        {editingMsg && (
          <View style={styles.replyBar}>
            <Ionicons name="create-outline" size={20} color={COLORS.primary} />
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={styles.replyBarSender}>Editing message</Text>
              <Text style={styles.replyBarContent} numberOfLines={1}>{editingMsg.content}</Text>
            </View>
            <TouchableOpacity onPress={() => { setEditingMsg(null); setText(""); }} style={{ padding: 4 }}>
              <Ionicons name="close" size={18} color={COLORS.textMuted} />
            </TouchableOpacity>
          </View>
        )}

        {/* Reply bar */}
        {!editingMsg && replyingTo && (
          <View style={styles.replyBar}>
            <View style={styles.replyBarAccent} />
            <View style={{ flex: 1 }}>
              <Text style={styles.replyBarSender}>{replyingTo.sender}</Text>
              <Text style={styles.replyBarContent} numberOfLines={1}>
                {replyingTo.message_type === "image" ? "📷 Photo"
                  : replyingTo.message_type === "voice" ? "🎤 Voice message"
                  : replyingTo.message_type === "video" ? "🎥 Video"
                  : replyingTo.content}
              </Text>
            </View>
            <TouchableOpacity onPress={() => setReplyingTo(null)} style={{ padding: 4 }}>
              <Ionicons name="close" size={18} color={COLORS.textMuted} />
            </TouchableOpacity>
          </View>
        )}

        {/* Pending media preview */}
        {pendingImage && (
          <View style={styles.previewBar}>
            {pendingMediaType === "image"
              ? <Image source={{ uri: pendingImage }} style={styles.previewThumb} />
              : (
                <View style={[styles.previewThumb, { backgroundColor: COLORS.primaryBg, justifyContent: "center", alignItems: "center" }]}>
                  <Ionicons name="videocam" size={28} color={COLORS.primary} />
                </View>
              )
            }
            <TouchableOpacity style={styles.previewRemove} onPress={() => { setPendingImage(null); setPendingMediaType("image"); }}>
              <Ionicons name="close-circle" size={22} color={COLORS.error} />
            </TouchableOpacity>
          </View>
        )}

        {/* Input bar */}
        {isRecording ? (
          <View style={styles.recordingBar}>
            <TouchableOpacity onPress={cancelRecording} style={styles.iconBtn}>
              <Ionicons name="trash-outline" size={24} color={COLORS.error} />
            </TouchableOpacity>
            <View style={styles.recordingIndicator}>
              <View style={styles.recordingDot} />
              <Text style={styles.recordingTime}>{formatDuration(recordingDuration)}</Text>
              <Text style={styles.recordingHint}>Recording…</Text>
            </View>
            <TouchableOpacity
              style={[styles.sendBtn, { backgroundColor: COLORS.success ?? COLORS.primary }]}
              onPress={stopAndSendRecording}
              disabled={sending}
            >
              {sending
                ? <ActivityIndicator size="small" color={COLORS.white} />
                : <Ionicons name="checkmark" size={20} color={COLORS.white} />}
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.inputBar}>
            <TouchableOpacity style={styles.iconBtn} onPress={() => setEmojiOpen((v) => !v)}>
              <Ionicons name={emojiOpen ? "happy" : "happy-outline"} size={24} color={emojiOpen ? COLORS.primary : COLORS.textMuted} />
            </TouchableOpacity>
            <TouchableOpacity style={styles.iconBtn} onPress={showAttachmentSheet}>
              <Ionicons name="attach" size={24} color={COLORS.textMuted} />
            </TouchableOpacity>
            <TextInput
              placeholder="Type a message..."
              placeholderTextColor={COLORS.textMuted}
              value={text}
              onChangeText={handleTextChange}
              onFocus={() => setEmojiOpen(false)}
              style={styles.input}
              multiline
              maxLength={2000}
            />
            <TouchableOpacity
              style={[styles.sendBtn, (!canSend && !canRecord) && styles.sendDisabled]}
              onPress={canSend ? send : canRecord ? startRecording : undefined}
              disabled={!canSend && !canRecord}
            >
              {sending
                ? <ActivityIndicator size="small" color={COLORS.white} />
                : canSend
                  ? <Ionicons name="send" size={18} color={COLORS.white} />
                  : <Ionicons name="mic" size={20} color={COLORS.white} />}
            </TouchableOpacity>
          </View>
        )}
      </KeyboardAvoidingView>

      {insets.bottom > 0 && <View style={{ height: insets.bottom, backgroundColor: COLORS.white }} />}

      <EmojiKeyboard
        onEmojiSelected={(emoji) => setText((t) => t + emoji.emoji)}
        open={emojiOpen}
        onClose={() => setEmojiOpen(false)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.white },
  flex: { flex: 1 },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  emptyText: { color: COLORS.textMuted, fontSize: FONTS.md, textAlign: "center", lineHeight: 24 },

  list: { paddingHorizontal: 12, paddingVertical: 16, paddingBottom: 8, flexGrow: 1, backgroundColor: COLORS.background },

  rowMe: { flexDirection: "row", justifyContent: "flex-end", marginVertical: 2, paddingLeft: 48 },
  bubbleMe: {
    backgroundColor: COLORS.messageSent,
    borderRadius: 18, borderBottomRightRadius: 4,
    paddingHorizontal: 14, paddingVertical: 8,
  },
  textMe: { fontSize: FONTS.md, color: COLORS.messageSentText, lineHeight: 20 },
  metaRow: { flexDirection: "row", alignItems: "center", alignSelf: "flex-end", gap: 4, marginTop: 3 },
  editedLabel: { fontSize: 10, color: "rgba(255,255,255,0.55)", fontStyle: "italic" },
  timeMe: { fontSize: 10, color: "rgba(255,255,255,0.6)" },

  rowThem: { flexDirection: "row", alignItems: "flex-end", marginVertical: 2, paddingRight: 48, gap: 6 },
  bubbleThem: {
    backgroundColor: COLORS.white,
    borderRadius: 18, borderBottomLeftRadius: 4,
    paddingHorizontal: 14, paddingVertical: 8,
    borderWidth: 1, borderColor: COLORS.border,
  },
  bubbleImage: { padding: 4 },
  msgImage: { width: 220, height: 160, borderRadius: 12, marginBottom: 4 },
  videoPlaceholder: {
    width: 180, height: 120, borderRadius: 12, marginBottom: 4,
    backgroundColor: "rgba(0,0,0,0.25)", justifyContent: "center", alignItems: "center",
  },
  senderName: { fontSize: 11, fontWeight: "700", color: COLORS.primary, marginBottom: 3, marginLeft: 2 },
  textThem: { fontSize: FONTS.md, color: COLORS.messageReceivedText, lineHeight: 20 },
  timeThem: { fontSize: 10, color: COLORS.textMuted },

  // Voice bubble
  voiceBubble: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 4, minWidth: 160 },
  voiceWave: { flexDirection: "row", alignItems: "center", gap: 2, flex: 1 },
  voiceBar: { width: 3, borderRadius: 2 },

  // Reactions
  reactionsRow: { flexDirection: "row", flexWrap: "wrap", gap: 4, marginTop: 2, paddingLeft: 48, paddingRight: 8 },
  reactionsRowMe: { justifyContent: "flex-end", paddingLeft: 8, paddingRight: 4 },
  reactionChip: {
    flexDirection: "row", alignItems: "center", gap: 3,
    backgroundColor: COLORS.white, borderWidth: 1, borderColor: COLORS.border,
    borderRadius: 12, paddingHorizontal: 7, paddingVertical: 3,
  },
  reactionChipMine: { backgroundColor: COLORS.primaryBg, borderColor: COLORS.primary },
  reactionEmoji: { fontSize: 14 },
  reactionCount: { fontSize: 11, color: COLORS.textSecondary, fontWeight: "600" },

  // Unread divider
  unreadDivider: { flexDirection: "row", alignItems: "center", marginVertical: 12, paddingHorizontal: 12, gap: 8 },
  unreadDividerLine: { flex: 1, height: 1, backgroundColor: COLORS.primary, opacity: 0.35 },
  unreadDividerLabel: {
    fontSize: 11, fontWeight: "700", color: COLORS.primary,
    paddingHorizontal: 8, paddingVertical: 3,
    borderRadius: RADIUS.full, backgroundColor: COLORS.primaryBg, overflow: "hidden",
  },

  // Typing
  typingBar: { paddingHorizontal: 16, paddingVertical: 4, backgroundColor: COLORS.background },
  typingText: { fontSize: 12, color: COLORS.textMuted, fontStyle: "italic" },

  // Reply / edit bar
  replyBar: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 14, paddingVertical: 8, gap: 10,
    backgroundColor: COLORS.primaryBg,
    borderTopWidth: 1, borderTopColor: COLORS.border,
  },
  replyBarAccent: { width: 3, alignSelf: "stretch", borderRadius: 2, backgroundColor: COLORS.primary },
  replyBarSender: { fontSize: 12, fontWeight: "700", color: COLORS.primary, marginBottom: 2 },
  replyBarContent: { fontSize: 12, color: COLORS.textSecondary },

  // Reply quote inside bubble
  replyQuote: { borderRadius: 8, padding: 8, marginBottom: 6, borderLeftWidth: 3 },
  replyQuoteMe: { backgroundColor: "rgba(0,0,0,0.15)", borderLeftColor: "rgba(255,255,255,0.6)" },
  replyQuoteThem: { backgroundColor: COLORS.primaryBg, borderLeftColor: COLORS.primary },
  replyQuoteSender: { fontSize: 11, fontWeight: "700", color: COLORS.primary, marginBottom: 2 },
  replyQuoteContent: { fontSize: 12, color: COLORS.textSecondary, lineHeight: 16 },

  // Media preview
  previewBar: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 12, paddingVertical: 8,
    backgroundColor: COLORS.background,
    borderTopWidth: 1, borderTopColor: COLORS.border,
  },
  previewThumb: { width: 64, height: 64, borderRadius: 8 },
  previewRemove: { marginLeft: 8 },

  // Recording bar
  recordingBar: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 8, paddingVertical: 10,
    backgroundColor: COLORS.white,
    borderTopWidth: 1, borderTopColor: COLORS.border,
    gap: 8,
  },
  recordingIndicator: { flex: 1, flexDirection: "row", alignItems: "center", gap: 8 },
  recordingDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.error },
  recordingTime: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.error },
  recordingHint: { fontSize: 12, color: COLORS.textMuted },

  // Input bar
  inputBar: {
    flexDirection: "row", alignItems: "flex-end",
    paddingHorizontal: 8, paddingVertical: 10,
    backgroundColor: COLORS.white,
    borderTopWidth: 1, borderTopColor: COLORS.border,
    gap: 6,
  },
  iconBtn: { paddingHorizontal: 4, paddingBottom: 10 },
  input: {
    flex: 1,
    borderWidth: 1.5, borderColor: COLORS.border,
    borderRadius: 24, paddingHorizontal: 14, paddingVertical: 10,
    fontSize: FONTS.md, color: COLORS.text,
    backgroundColor: COLORS.background,
    maxHeight: 120,
  },
  sendBtn: {
    width: 44, height: 44, borderRadius: RADIUS.full,
    backgroundColor: COLORS.primary,
    justifyContent: "center", alignItems: "center",
  },
  sendDisabled: { backgroundColor: COLORS.textMuted },

  // Menus
  menuOverlay: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.3)",
    justifyContent: "flex-start", alignItems: "flex-end",
    paddingTop: 90, paddingRight: 16,
  },
  msgMenuOverlay: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "center", alignItems: "center",
  },
  menuCard: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    paddingVertical: 8, minWidth: 220,
    shadowColor: "#000", shadowOpacity: 0.15, shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 }, elevation: 8,
  },
  msgMenuCard: {
    backgroundColor: COLORS.white, borderRadius: RADIUS.lg,
    paddingVertical: 8, minWidth: 240, maxWidth: 300,
    shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 }, elevation: 10,
  },
  quickReactions: {
    flexDirection: "row", justifyContent: "space-around",
    paddingHorizontal: 8, paddingVertical: 10,
  },
  quickReactionBtn: { padding: 6 },
  quickReactionEmoji: { fontSize: 28 },
  menuItem: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 14, gap: 12 },
  menuItemText: { fontSize: FONTS.md, fontWeight: "500", color: COLORS.text },
  menuDivider: { height: 1, backgroundColor: COLORS.border, marginHorizontal: 12 },

  // Selection mode
  selectionHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: COLORS.primary,
    paddingHorizontal: 8, paddingVertical: 12, paddingTop: 16,
  },
  selectionHeaderBtn: { padding: 8 },
  selectionCount: { fontSize: FONTS.md, fontWeight: "700", color: COLORS.white, flex: 1, marginLeft: 8 },
  selectableRow: { borderRadius: 4 },
  selectedRow: { backgroundColor: COLORS.primaryBg },
  selectCircleWrap: { justifyContent: "center", alignItems: "center", paddingLeft: 8, paddingRight: 4 },
  selectCircle: {
    width: 22, height: 22, borderRadius: 11,
    borderWidth: 2, borderColor: COLORS.textMuted,
    justifyContent: "center", alignItems: "center",
    backgroundColor: COLORS.white,
  },
  selectCircleActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
});
