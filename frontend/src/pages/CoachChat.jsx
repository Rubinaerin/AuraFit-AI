import React, { useState } from "react";
import { Send, Bot, User as UserIcon } from "lucide-react";

export default function CoachChat() {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Hi Rubina! I'm FitCoach AI, your personal training assistant. I know your profile and health conditions, so I'll always give you safe guidance. How can I help you today?" }
  ]);
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg = { role: "user", content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    
    setTimeout(() => {
      setMessages(prev => [...prev, { role: "assistant", content: "Understood. Based on your profile guidelines, I recommend prioritizing neutral spine alignment and keeping the weight light for lower body movements." }]);
    }, 1000);
  };

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="border-b border-border pb-4">
        <h2 className="font-display text-2xl font-bold">FitCoach AI</h2>
        <p className="text-xs text-text-secondary">Your injury-aware personal training assistant</p>
      </div>
      <div className="bg-surface border border-border rounded-2xl h-[450px] p-4 overflow-y-auto space-y-4">
        {messages.map((msg, i) => (
          <div key={i} className={`flex items-start gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${msg.role === "user" ? "bg-primary/20 text-primary" : "bg-accent/20 text-accent"}`}>
              {msg.role === "user" ? <UserIcon size={14} /> : <Bot size={14} />}
            </div>
            <div className={`p-3 rounded-2xl text-sm max-w-[70%] ${msg.role === "user" ? "bg-primary/10" : "bg-card border border-border"}`}>
              {msg.content}
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input 
          value={input} 
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && handleSend()}
          placeholder="Ask FitCoach anything..." 
          className="input-field" 
        />
        <button onClick={handleSend} className="btn-primary"><Send size={14} /></button>
      </div>
    </div>
  );
}