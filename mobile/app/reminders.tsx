import { useEffect, useState } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
  ActivityIndicator,
  RefreshControl,
  Platform,
  Modal,
  Pressable,
  KeyboardAvoidingView,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import {
  getReminders,
  createReminder,
  updateReminder,
  deleteReminder,
  type Reminder,
  type ReminderType,
  type Recurrence,
  type CreateReminderPayload,
} from "../api/reminders";
import { COLORS, FONTS, RADIUS } from "../constants/theme";
import AppHeader from "../components/app/AppHeader";
import FAB from "../components/app/FAB";

// ─── Constants ───────────────────────────────────────────────────────────────

const TYPE_META: Record<ReminderType, { icon: string; label: string; color: string }> = {
  contribution_due:  { icon: "wallet-outline",       label: "Contribution",   color: COLORS.primary },
  welfare_contrib:   { icon: "heart-outline",         label: "Welfare",        color: "#E05C5C" },
  advance_repayment: { icon: "trending-up-outline",   label: "Repayment",      color: COLORS.accent },
  standing_order:    { icon: "repeat-outline",        label: "Standing Order", color: "#5C7AE0" },
  custom:            { icon: "create-outline",        label: "Custom",         color: COLORS.textSecondary },
};

const RECURRENCE_OPTS: { value: Recurrence; label: string }[] = [
  { value: "none",    label: "Once"    },
  { value: "daily",   label: "Daily"   },
  { value: "weekly",  label: "Weekly"  },
  { value: "monthly", label: "Monthly" },
];

const TYPE_OPTS = Object.entries(TYPE_META).map(([k, v]) => ({
  value: k as ReminderType,
  ...v,
}));

// Quick date offsets (days from today)
const DATE_PRESETS = [
  { label: "Today",    days: 0 },
  { label: "Tomorrow", days: 1 },
  { label: "+3 days",  days: 3 },
  { label: "+1 week",  days: 7 },
];

// Quick time presets (hour in 24h)
const TIME_PRESETS = [
  { label: "8 AM",  hour: 8  },
  { label: "12 PM", hour: 12 },
  { label: "3 PM",  hour: 15 },
  { label: "6 PM",  hour: 18 },
  { label: "9 PM",  hour: 21 },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtDateTime(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-KE", {
    weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  });
}

function buildISO(days: number, hour: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString();
}

// ─── Reminder Card ───────────────────────────────────────────────────────────

function ReminderCard({
  item,
  onToggle,
  onEdit,
  onDelete,
}: {
  item:     Reminder;
  onToggle: (id: number, val: boolean) => void;
  onEdit:   (item: Reminder) => void;
  onDelete: (id: number) => void;
}) {
  const meta = TYPE_META[item.reminder_type] ?? TYPE_META.custom;
  const overdue = item.is_overdue && item.is_active;

  return (
    <View style={[rc.card, overdue && rc.cardOverdue]}>
      {/* Icon col */}
      <View style={[rc.iconWrap, { backgroundColor: meta.color + "18" }]}>
        <Ionicons name={meta.icon as any} size={20} color={meta.color} />
      </View>

      {/* Content col */}
      <View style={rc.content}>
        <View style={rc.row}>
          <Text style={rc.title} numberOfLines={1}>{item.title}</Text>
          {overdue && (
            <View style={rc.overdueTag}>
              <Text style={rc.overdueTagText}>Overdue</Text>
            </View>
          )}
        </View>

        <Text style={rc.meta}>
          {fmtDateTime(item.next_fire_at)}
          {item.recurrence !== "none" && (
            <Text style={rc.recurrence}>  ·  {item.recurrence}</Text>
          )}
        </Text>

        {item.note ? (
          <Text style={rc.note} numberOfLines={1}>{item.note}</Text>
        ) : null}
      </View>

      {/* Action col */}
      <View style={rc.actions}>
        <TouchableOpacity onPress={() => onToggle(item.id, !item.is_active)} style={rc.actionBtn}>
          <Ionicons
            name={item.is_active ? "notifications" : "notifications-off-outline"}
            size={18}
            color={item.is_active ? COLORS.primary : COLORS.textMuted}
          />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => onEdit(item)} style={rc.actionBtn}>
          <Ionicons name="pencil-outline" size={16} color={COLORS.textMuted} />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => onDelete(item.id)} style={rc.actionBtn}>
          <Ionicons name="trash-outline" size={16} color={COLORS.error + "90"} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const rc = StyleSheet.create({
  card: {
    flexDirection: "row",
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    padding: 14,
    marginBottom: 10,
    alignItems: "flex-start",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  cardOverdue: {
    borderLeftWidth: 3,
    borderLeftColor: COLORS.error,
  },
  iconWrap: {
    width: 40, height: 40,
    borderRadius: RADIUS.md,
    justifyContent: "center",
    alignItems: "center",
    marginRight: 12,
    marginTop: 2,
  },
  content: { flex: 1 },
  row:  { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 3 },
  title: { fontSize: FONTS.md, fontWeight: "600", color: COLORS.text, flex: 1 },
  overdueTag: {
    backgroundColor: COLORS.error + "18",
    borderRadius: RADIUS.full,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  overdueTagText: { fontSize: FONTS.xs, color: COLORS.error, fontWeight: "700" },
  meta: { fontSize: FONTS.sm, color: COLORS.textSecondary },
  recurrence: { color: COLORS.primary, fontWeight: "600" },
  note: { fontSize: FONTS.sm, color: COLORS.textMuted, marginTop: 3 },
  actions: { flexDirection: "column", gap: 4, marginLeft: 8 },
  actionBtn: {
    width: 30, height: 30,
    justifyContent: "center",
    alignItems: "center",
  },
});

// ─── Create / Edit Sheet ──────────────────────────────────────────────────────

type FormState = {
  title:      string;
  type:       ReminderType;
  note:       string;
  recurrence: Recurrence;
  days:       number;
  hour:       number;
};

const BLANK_FORM: FormState = {
  title:      "",
  type:       "custom",
  note:       "",
  recurrence: "none",
  days:       1,
  hour:       9,
};

function ReminderSheet({
  visible,
  editing,
  onClose,
  onSave,
  saving,
}: {
  visible: boolean;
  editing: Reminder | null;
  onClose: () => void;
  onSave:  (form: FormState) => Promise<void>;
  saving:  boolean;
}) {
  const [form, setForm] = useState<FormState>(BLANK_FORM);

  useEffect(() => {
    if (visible) {
      if (editing) {
        const d = new Date(editing.scheduled_for);
        setForm({
          title:      editing.title,
          type:       editing.reminder_type,
          note:       editing.note ?? "",
          recurrence: editing.recurrence,
          days:       0,   // not used when editing
          hour:       d.getHours(),
        });
      } else {
        setForm(BLANK_FORM);
      }
    }
  }, [visible, editing]);

  const set = (k: keyof FormState, v: any) => setForm(f => ({ ...f, [k]: v }));

  const previewDt = () => {
    if (editing) return fmtDateTime(editing.scheduled_for);
    const d = new Date();
    d.setDate(d.getDate() + form.days);
    d.setHours(form.hour, 0, 0, 0);
    return d.toLocaleDateString("en-KE", {
      weekday: "short", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit",
    });
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <Pressable style={sh.backdrop} onPress={onClose}>
          <Pressable style={sh.sheet} onStartShouldSetResponder={() => true}>
            <View style={sh.handle} />
            <Text style={sh.title}>{editing ? "Edit Reminder" : "New Reminder"}</Text>

            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">

              {/* ── Title ── */}
              <Text style={sh.label}>Title</Text>
              <TextInput
                value={form.title}
                onChangeText={v => set("title", v)}
                placeholder="e.g. Pay chama contribution"
                placeholderTextColor={COLORS.textMuted}
                style={sh.input}
                autoFocus
                maxLength={80}
              />

              {/* ── Type ── */}
              <Text style={sh.label}>Type</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={sh.chipRow}>
                {TYPE_OPTS.map(t => (
                  <TouchableOpacity
                    key={t.value}
                    style={[sh.chip, form.type === t.value && { backgroundColor: t.color + "20", borderColor: t.color }]}
                    onPress={() => set("type", t.value)}
                  >
                    <Ionicons name={t.icon as any} size={14} color={form.type === t.value ? t.color : COLORS.textMuted} />
                    <Text style={[sh.chipText, form.type === t.value && { color: t.color, fontWeight: "700" }]}>
                      {t.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              {/* ── Date (skip when editing — use existing date) ── */}
              {!editing && (
                <>
                  <Text style={sh.label}>Date</Text>
                  <View style={sh.presetRow}>
                    {DATE_PRESETS.map(p => (
                      <TouchableOpacity
                        key={p.days}
                        style={[sh.preset, form.days === p.days && sh.presetActive]}
                        onPress={() => set("days", p.days)}
                      >
                        <Text style={[sh.presetText, form.days === p.days && sh.presetTextActive]}>
                          {p.label}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </>
              )}

              {/* ── Time ── */}
              <Text style={sh.label}>Time</Text>
              <View style={sh.presetRow}>
                {TIME_PRESETS.map(p => (
                  <TouchableOpacity
                    key={p.hour}
                    style={[sh.preset, form.hour === p.hour && sh.presetActive]}
                    onPress={() => set("hour", p.hour)}
                  >
                    <Text style={[sh.presetText, form.hour === p.hour && sh.presetTextActive]}>
                      {p.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* ── Scheduled preview ── */}
              <View style={sh.dtPreview}>
                <Ionicons name="calendar-outline" size={15} color={COLORS.primary} />
                <Text style={sh.dtPreviewText}>{previewDt()}</Text>
              </View>

              {/* ── Recurrence ── */}
              <Text style={sh.label}>Repeat</Text>
              <View style={sh.presetRow}>
                {RECURRENCE_OPTS.map(r => (
                  <TouchableOpacity
                    key={r.value}
                    style={[sh.preset, form.recurrence === r.value && sh.presetActive]}
                    onPress={() => set("recurrence", r.value)}
                  >
                    <Text style={[sh.presetText, form.recurrence === r.value && sh.presetTextActive]}>
                      {r.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* ── Note ── */}
              <Text style={sh.label}>Note (optional)</Text>
              <TextInput
                value={form.note}
                onChangeText={v => set("note", v)}
                placeholder="Additional details..."
                placeholderTextColor={COLORS.textMuted}
                style={[sh.input, sh.textarea]}
                multiline
                maxLength={200}
              />

              {/* ── Save ── */}
              <TouchableOpacity
                style={[sh.saveBtn, saving && { opacity: 0.6 }]}
                onPress={() => onSave(form)}
                disabled={saving}
              >
                {saving
                  ? <ActivityIndicator color={COLORS.white} size="small" />
                  : <Text style={sh.saveBtnText}>{editing ? "Update Reminder" : "Set Reminder"}</Text>
                }
              </TouchableOpacity>
              <View style={{ height: 20 }} />
            </ScrollView>
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const sh = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    padding: 20,
    maxHeight: "92%",
    paddingBottom: Platform.OS === "ios" ? 34 : 20,
  },
  handle: {
    width: 40, height: 4,
    backgroundColor: COLORS.border,
    borderRadius: RADIUS.full,
    alignSelf: "center",
    marginBottom: 16,
  },
  title: {
    fontSize: FONTS.lg,
    fontWeight: "700",
    color: COLORS.text,
    marginBottom: 16,
  },
  label: {
    fontSize: FONTS.sm,
    fontWeight: "600",
    color: COLORS.textSecondary,
    marginBottom: 8,
    marginTop: 4,
  },
  input: {
    borderWidth: 1.5,
    borderColor: COLORS.border,
    borderRadius: RADIUS.md,
    padding: 12,
    fontSize: FONTS.md,
    color: COLORS.text,
    backgroundColor: COLORS.background,
    marginBottom: 14,
  },
  textarea: {
    height: 70,
    textAlignVertical: "top",
  },
  chipRow: { marginBottom: 14 },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: RADIUS.full,
    borderWidth: 1.5,
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
    marginRight: 8,
  },
  chipText: { fontSize: FONTS.sm, color: COLORS.textMuted },
  presetRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 14,
  },
  preset: {
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: RADIUS.full,
    borderWidth: 1.5,
    borderColor: COLORS.border,
    backgroundColor: COLORS.background,
  },
  presetActive: {
    backgroundColor: COLORS.primary + "15",
    borderColor: COLORS.primary,
  },
  presetText:       { fontSize: FONTS.sm, color: COLORS.textMuted },
  presetTextActive: { fontSize: FONTS.sm, color: COLORS.primary, fontWeight: "700" },
  dtPreview: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: COLORS.primaryPale,
    borderRadius: RADIUS.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginBottom: 14,
  },
  dtPreviewText: {
    fontSize: FONTS.sm,
    color: COLORS.primary,
    fontWeight: "600",
  },
  saveBtn: {
    backgroundColor: COLORS.primary,
    borderRadius: RADIUS.md,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 8,
  },
  saveBtnText: {
    color: COLORS.white,
    fontWeight: "700",
    fontSize: FONTS.md,
  },
});

// ─── Main Screen ─────────────────────────────────────────────────────────────

export default function RemindersScreen() {
  const [reminders,   setReminders]   = useState<Reminder[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [refreshing,  setRefreshing]  = useState(false);
  const [showSheet,   setShowSheet]   = useState(false);
  const [editing,     setEditing]     = useState<Reminder | null>(null);
  const [saving,      setSaving]      = useState(false);
  const [showInactive, setShowInactive] = useState(false);

  async function loadReminders(showAll = false) {
    try {
      // getReminders(true)  → active-only,  getReminders(false) → all reminders
      const data = await getReminders(!showAll);
      setReminders(data);
    } catch {
      Alert.alert("Error", "Could not load reminders.");
    }
  }

  useEffect(() => {
    loadReminders(showInactive).finally(() => setLoading(false));
  }, [showInactive]);

  async function onRefresh() {
    setRefreshing(true);
    await loadReminders(showInactive);
    setRefreshing(false);
  }

  function openCreate() {
    setEditing(null);
    setShowSheet(true);
  }

  function openEdit(item: Reminder) {
    setEditing(item);
    setShowSheet(true);
  }

  async function handleToggle(id: number, isActive: boolean) {
    try {
      const updated = await updateReminder(id, { is_active: isActive });
      setReminders(prev => prev.map(r => r.id === id ? updated : r));
    } catch {
      Alert.alert("Error", "Could not update reminder.");
    }
  }

  function confirmDelete(id: number) {
    Alert.alert(
      "Delete Reminder",
      "Are you sure you want to delete this reminder?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text:    "Delete",
          style:   "destructive",
          onPress: async () => {
            try {
              await deleteReminder(id);
              setReminders(prev => prev.filter(r => r.id !== id));
            } catch {
              Alert.alert("Error", "Could not delete reminder.");
            }
          },
        },
      ]
    );
  }

  async function handleSave(form: FormState) {
    if (!form.title.trim()) {
      Alert.alert("Title required", "Please enter a reminder title.");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        // Update existing
        const updates: any = {
          title:      form.title.trim(),
          note:       form.note.trim(),
          recurrence: form.recurrence,
        };
        // Only update time (keep existing date, change hour)
        const orig = new Date(editing.scheduled_for);
        orig.setHours(form.hour, 0, 0, 0);
        updates.scheduled_for = orig.toISOString();
        const updated = await updateReminder(editing.id, updates);
        setReminders(prev => prev.map(r => r.id === editing.id ? updated : r));
      } else {
        const payload: CreateReminderPayload = {
          reminder_type: form.type,
          title:         form.title.trim(),
          note:          form.note.trim() || undefined,
          scheduled_for: buildISO(form.days, form.hour),
          recurrence:    form.recurrence,
        };
        const created = await createReminder(payload);
        setReminders(prev => [created, ...prev]);
      }
      setShowSheet(false);
    } catch (e: any) {
      const msg = e?.response?.data?.detail ?? e?.response?.data?.scheduled_for?.[0] ?? "Could not save reminder.";
      Alert.alert("Error", msg);
    } finally {
      setSaving(false);
    }
  }

  // Partition
  const overdue   = reminders.filter(r => r.is_overdue && r.is_active);
  const active    = reminders.filter(r => !r.is_overdue && r.is_active);
  const inactive  = reminders.filter(r => !r.is_active);

  const isEmpty = reminders.length === 0;

  return (
    <SafeAreaView style={ms.safe}>
      <AppHeader
        title="Reminders"
        variant="light"
        leading="back"
        rightExtra={
          <TouchableOpacity
            style={ms.toggleBtn}
            onPress={() => setShowInactive(v => !v)}
          >
            <Text style={ms.toggleBtnText}>
              {showInactive ? "Active only" : "Show all"}
            </Text>
          </TouchableOpacity>
        }
      />

      {loading ? (
        <View style={ms.center}>
          <ActivityIndicator color={COLORS.primary} size="large" />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={ms.body}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
          showsVerticalScrollIndicator={false}
        >
          {isEmpty ? (
            <View style={ms.empty}>
              <Ionicons name="alarm-outline" size={52} color={COLORS.border} />
              <Text style={ms.emptyTitle}>No reminders yet</Text>
              <Text style={ms.emptyBody}>
                Tap the + button to set a reminder for contributions, repayments, or any custom event.
              </Text>
            </View>
          ) : (
            <>
              {/* ── Overdue ── */}
              {overdue.length > 0 && (
                <>
                  <View style={ms.sectionRow}>
                    <View style={ms.overdueBar} />
                    <Text style={[ms.sectionTitle, { color: COLORS.error }]}>Overdue ({overdue.length})</Text>
                  </View>
                  {overdue.map(r => (
                    <ReminderCard
                      key={r.id}
                      item={r}
                      onToggle={handleToggle}
                      onEdit={openEdit}
                      onDelete={confirmDelete}
                    />
                  ))}
                </>
              )}

              {/* ── Upcoming ── */}
              {active.length > 0 && (
                <>
                  <Text style={ms.sectionTitle}>Upcoming ({active.length})</Text>
                  {active.map(r => (
                    <ReminderCard
                      key={r.id}
                      item={r}
                      onToggle={handleToggle}
                      onEdit={openEdit}
                      onDelete={confirmDelete}
                    />
                  ))}
                </>
              )}

              {/* ── Inactive (only when showInactive) ── */}
              {showInactive && inactive.length > 0 && (
                <>
                  <Text style={[ms.sectionTitle, { color: COLORS.textMuted }]}>
                    Paused ({inactive.length})
                  </Text>
                  {inactive.map(r => (
                    <View key={r.id} style={{ opacity: 0.55 }}>
                      <ReminderCard
                        item={r}
                        onToggle={handleToggle}
                        onEdit={openEdit}
                        onDelete={confirmDelete}
                      />
                    </View>
                  ))}
                </>
              )}
            </>
          )}

          {/* Stats footer */}
          {!isEmpty && (
            <View style={ms.statsRow}>
              <View style={ms.statPill}>
                <Text style={ms.statNum}>{reminders.filter(r => r.is_active).length}</Text>
                <Text style={ms.statLabel}>Active</Text>
              </View>
              <View style={ms.statPill}>
                <Text style={[ms.statNum, { color: COLORS.error }]}>{overdue.length}</Text>
                <Text style={ms.statLabel}>Overdue</Text>
              </View>
              <View style={ms.statPill}>
                <Text style={ms.statNum}>{reminders.filter(r => r.recurrence !== "none").length}</Text>
                <Text style={ms.statLabel}>Recurring</Text>
              </View>
            </View>
          )}

          <View style={{ height: 100 }} />
        </ScrollView>
      )}

      <FAB onPress={openCreate} />

      <ReminderSheet
        visible={showSheet}
        editing={editing}
        onClose={() => setShowSheet(false)}
        onSave={handleSave}
        saving={saving}
      />
    </SafeAreaView>
  );
}

// ─── Styles ──────────────────────────────────────────────────────────────────

const ms = StyleSheet.create({
  safe:   { flex: 1, backgroundColor: COLORS.background },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  body:   { padding: 16 },

  toggleBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: COLORS.primaryPale,
    borderRadius: RADIUS.full,
    marginRight: 4,
  },
  toggleBtnText: {
    fontSize: FONTS.xs,
    color: COLORS.primary,
    fontWeight: "700",
  },

  sectionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 10,
    marginTop: 4,
  },
  overdueBar: {
    width: 3, height: 16,
    backgroundColor: COLORS.error,
    borderRadius: RADIUS.full,
  },
  sectionTitle: {
    fontSize: FONTS.sm,
    fontWeight: "700",
    color: COLORS.text,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    marginBottom: 10,
    marginTop: 6,
  },

  empty: {
    alignItems: "center",
    paddingTop: 80,
    paddingHorizontal: 32,
    gap: 12,
  },
  emptyTitle: {
    fontSize: FONTS.lg,
    fontWeight: "700",
    color: COLORS.textSecondary,
  },
  emptyBody: {
    fontSize: FONTS.md,
    color: COLORS.textMuted,
    textAlign: "center",
    lineHeight: 22,
  },

  statsRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 20,
  },
  statPill: {
    flex: 1,
    backgroundColor: COLORS.white,
    borderRadius: RADIUS.lg,
    padding: 14,
    alignItems: "center",
    gap: 2,
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 1,
  },
  statNum:   { fontSize: FONTS.xl, fontWeight: "700", color: COLORS.primary },
  statLabel: { fontSize: FONTS.xs, color: COLORS.textMuted, fontWeight: "600" },
});
