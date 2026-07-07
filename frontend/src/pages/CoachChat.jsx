import React, { useState, useRef, useEffect } from "react";
import { useOutletContext } from "react-router-dom";
import {
  Send, Bot, User as UserIcon, RefreshCw, CheckCheck,
  ArrowRightLeft, AlertTriangle, Plus, MessageSquareText,
} from "lucide-react";
import toast from "react-hot-toast";
import Topbar from "../components/layout/Topbar";
import Spinner from "../components/ui/Spinner";
import { chatService } from "../services/chatService";
import { useAuth } from "../hooks/useAuth";

/** Renders a PLAN_UPDATE block as a styled swap card */
function PlanUpdateCard({ update }) {
  if (!update) return null;
  return (
    <div className="mt-3 p-3 rounded-xl bg-accent/5 border border-accent/20 space-y-2">
      <div className="flex items-center gap-2">
        <ArrowRightLeft size={14} className="text-accent" />
        <span className="text-xs font-semibold text-accent">Program Update Suggested</span>
      </div>
      <div className="flex items-center gap-2 text-sm">
        <span className="px-2 py-0.5 rounded bg-danger/10 text-danger text-xs line-through">
          {update.old_exercise}
        </span>
        <ArrowRightLeft size={12} className="text-text-muted" />
        <span className="px-2 py-0.5 rounded bg-accent/10 text-accent text-xs font-medium">
          {update.new_exercise}
        </span>
      </div>
      {update.reason && (
        <p className="text-xs text-text-secondary">{update.reason}</p>
      )}
      {(update.sets || update.reps) && (
        <p className="text-xs text-text-muted">
          {update.sets} sets × {update.reps}  · rest {update.rest_seconds}s
        </p>
      )}
    </div>
  );
}

/** A single chat message bubble */
function Message({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex items-end gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"} animate-fade-in`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mb-0.5 ${
        isUser ? "bg-primary/20" : "bg-accent/15"
      }`}>
        {isUser
          ? <UserIcon size={13} className="text-primary" />
          : <Bot size={13} className="text-accent" />
        }
      </div>
      <div className={`max-w-[75%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
        {isUser ? (
          <div className="bubble-user">{msg.content}</div>
        ) : (
          <div className="bubble-bot">
            <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            {msg.plan_update && <PlanUpdateCard update={msg.plan_update} />}
          </div>
        )}
        <span className="text-[10px] text-text-muted px-1">{msg.time}</span>
      </div>
    </div>
  );
}

/** Typing indicator */
function TypingIndicator() {
  return (
    <div className="flex items-end gap-2.5">
      <div className="w-7 h-7 rounded-full bg-accent/15 flex items-center justify-center shrink-0">
        <Bot size={13} className="text-accent" />
      </div>
      <div className="bubble-bot px-4 py-3">
        <div className="flex gap-1 items-center h-4">
          {[0, 150, 300].map((d) => (
            <span
              key={d}
              className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce"
              style={{ animationDelay: `${d}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "I felt pain in my lower back during the last workout. What should I do?",
  "Can you give me an alternative to deadlifts that's safe for my condition?",
  "How many sets should I do if I'm feeling tired today?",
  "What should I eat before a morning workout session?",
];

export default function CoachChat() {
  const { user } = useAuth();
  const { onMenuClick } = useOutletContext() || {};

  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "assistant",
      content: `Hi ${user?.full_name?.split(" ")[0] || "there"}! I'm FitCoach AI, your personal training assistant. I know your profile and any health conditions you've registered, so I'll always give you safe, personalized guidance. How can I help you today?`,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const sendMessage = async (text) => {
    const content = (text || input).trim();
    if (!content || sending) return;
    setInput("");

    const userMsg = {
      id: Date.now() + "-u",
      role: "user",
      content,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setMessages((m) => [...m, userMsg]);
    setSending(true);

    try {
      const res = await chatService.sendMessage({
        message: content,
        session_id: sessionId,
        plan_name: null,      // Wire in from WorkoutEngine store in a future iteration
        primary_goal: user?.primary_goal,
      });

      if (!sessionId) setSessionId(res.session_id);

      const botMsg = {
        id: Date.now() + "-b",
        role: "assistant",
        content: res.reply,
        plan_update: res.plan_update || null,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((m) => [...m, botMsg]);

      if (res.plan_update) {
        toast.success("FitCoach suggested a program update!", { duration: 4000 });
      }
    } catch (err) {
      toast.error(err.message || "Failed to reach FitCoach.");
      setMessages((m) => [
        ...m,
        {
          id: Date.now() + "-e",
          role: "assistant",
          content: "Sorry, I couldn't connect to the server. Please try again.",
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const resetSession = () => {
    setMessages([{
      id: "welcome2",
      role: "assistant",
      content: "Session reset! I'm ready to help you again. What would you like to work on?",
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }]);
    setSessionId(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <>
      <Topbar
        title="FitCoach AI"
        subtitle="Your injury-aware personal training assistant — ask anything about your program"
        onMenuClick={onMenuClick}
        actions={
          <button onClick={resetSession} className="btn-ghost text-xs">
            <RefreshCw size={14} /> New Session
          </button>
        }
      />

      <div className="flex h-[calc(100vh-4rem)] flex-col lg:flex-row">
        {/* ── Left panel: session info ── */}
        <aside className="hidden lg:flex flex-col w-64 shrink-0 border-r border-border bg-surface">
          <div className="p-4 border-b border-border">
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-3">Session Info</p>
            <div className="space-y-2">
              <InfoRow label="User" value={user?.full_name} />
              <InfoRow label="Goal" value={user?.primary_goal?.replace(/_/g, " ")} />
              <InfoRow label="Level" value={user?.fitness_level} />
              <InfoRow
                label="Conditions"
                value={
                  user?.health_conditions?.filter((c) => c.is_active).length
                    ? user.health_conditions
                        .filter((c) => c.is_active)
                        .map((c) => c.condition_type.replace(/_/g, " "))
                        .join(", ")
                    : "None"
                }
              />
              <InfoRow label="Session ID" value={sessionId ? sessionId.slice(0, 8) + "…" : "Not started"} />
            </div>
          </div>

          {/* Safety notice */}
          <div className="p-4 border-b border-border">
            <div className="flex items-start gap-2 p-3 rounded-xl bg-warning/5 border border-warning/20">
              <AlertTriangle size={13} className="text-warning mt-0.5 shrink-0" />
              <p className="text-[11px] text-text-secondary leading-relaxed">
                FitCoach will never suggest exercises that conflict with your registered health conditions.
              </p>
            </div>
          </div>

          {/* Quick topics */}
          <div className="p-4 flex-1 overflow-y-auto">
            <p className="text-xs font-semibold text-text-secondary uppercase tracking-wide mb-2">
              Quick Questions
            </p>
            <div className="space-y-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  disabled={sending}
                  className="w-full text-left text-xs text-text-secondary hover:text-text-primary p-2 rounded-lg hover:bg-card transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <div className="p-3 border-t border-border flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <div className="glow-dot" />
              <span className="text-[11px] text-text-muted">AI Online</span>
            </div>
            <CheckCheck size={14} className="text-accent" />
          </div>
        </aside>

        {/* ── Main chat area ── */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 no-scrollbar">
            {messages.map((msg) => (
              <Message key={msg.id} msg={msg} />
            ))}
            {sending && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>

          {/* Mobile quick suggestions */}
          <div className="lg:hidden overflow-x-auto no-scrollbar px-4 pb-2">
            <div className="flex gap-2">
              {SUGGESTIONS.slice(0, 3).map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  disabled={sending}
                  className="shrink-0 text-[11px] text-text-secondary hover:text-text-primary px-3 py-1.5 rounded-full bg-surface border border-border whitespace-nowrap"
                >
                  {s.slice(0, 40)}…
                </button>
              ))}
            </div>
          </div>

          {/* Input bar */}
          <div className="border-t border-border p-4">
            <div className="flex items-end gap-3">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  placeholder="Ask FitCoach anything about your training…"
                  className="input-field pr-12 resize-none overflow-hidden"
                  style={{ minHeight: "44px", maxHeight: "120px" }}
                  onInput={(e) => {
                    e.target.style.height = "auto";
                    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                  }}
                />
                <button
                  onClick={() => sendMessage()}
                  disabled={!input.trim() || sending}
                  className="absolute right-3 bottom-2.5 w-8 h-8 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-40 flex items-center justify-center transition-colors"
                >
                  {sending ? <Spinner size={14} /> : <Send size={14} className="text-white" />}
                </button>
              </div>
            </div>
            <p className="text-[11px] text-text-muted mt-2 text-center">
              Press Enter to send · Shift+Enter for new line · FitCoach memory persists across sessions
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

function InfoRow({ label, value }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-[11px] text-text-muted shrink-0">{label}</span>
      <span className="text-[11px] text-text-primary text-right capitalize truncate">{value || "—"}</span>
    </div>
  );
}
