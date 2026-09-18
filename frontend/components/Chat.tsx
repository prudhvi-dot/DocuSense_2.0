"use client";

import { FormEvent, useEffect, useRef, useState, useTransition } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Loader2Icon, BotIcon } from "lucide-react";

export type Message = {
  id?: string;
  role: "human" | "ai";
  message: string;
  created_at: string;
};

type ChatProps = {
  docId: string;
  userName: string;
  initialMessages: Message[];
};

const Chat = ({ docId, userName, initialMessages }: ChatProps) => {
  const [isPending, startTransition] = useTransition();
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const divRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    divRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();

    const question = input.trim();

    if (!question || isPending) return;

    setInput("");
    setError(null);

    // Add user message immediately
    setMessages((prev) => [
      ...prev,
      {
        role: "human",
        message: question,
        created_at: new Date().toISOString(),
      },
    ]);

    startTransition(async () => {
      try {
        const res = await fetch(`/api/backend/chats/${docId}`, {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ question }),
});

        if (!res.ok) {
          const errorText = await res.text();

          console.error("Backend error:", errorText);

          throw new Error(
            `Backend error (${res.status}): ${errorText}`
          );
        }

        const data = await res.json();

        // Backend returns:
        // {
        //   "message": "complete AI response"
        // }

        setMessages((prev) => [
          ...prev,
          {
            role: "ai",
            message: data.message,
            created_at: new Date().toISOString(),
          },
        ]);
      } catch (error) {
        console.error(error);

        setError("Something went wrong. Please try again.");

        // Remove the user message if request failed
        setMessages((prev) => prev.slice(0, -1));
      }
    });
  }

  function getInitials(name: string) {
    return name
      .split(" ")
      .map((p) => p[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 w-full overflow-y-auto p-4 space-y-3">
        {messages.length === 0 ? (
          <p className="text-center text-gray-400">
            No messages yet. Start a conversation!
          </p>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={msg.id ?? idx}
              className={`flex mb-3.5 ${
                msg.role === "human"
                  ? "justify-start flex-row-reverse"
                  : "justify-start"
              }`}
            >
              <div className="flex items-end">
                {msg.role === "human" ? (
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-medium ml-1">
                    {getInitials(userName)}
                  </div>
                ) : (
                  <BotIcon className="w-7 h-7 mr-1" />
                )}
              </div>

              <div
                className={`relative max-w-[75%] p-3 text-sm shadow-md rounded-2xl break-words ${
                  msg.role === "human"
                    ? "bg-[#0f0f0f] text-white rounded-br-none"
                    : "bg-white text-black rounded-bl-none"
                }`}
              >
                <p>{msg.message}</p>

                <span className="block text-[10px] mt-1 opacity-60 text-right">
                  {new Date(msg.created_at).toLocaleTimeString("en-US", {
  hour: "2-digit",
  minute: "2-digit",
})}
                </span>
              </div>
            </div>
          ))
        )}

        {/* Scroll anchor */}
        <div ref={divRef}></div>
      </div>

      {error && (
        <p className="px-5 text-sm text-destructive">
          {error}
        </p>
      )}

      <form
        onSubmit={handleSubmit}
        className="flex sticky bottom-0 space-x-0 p-5 bg-neutral-800"
      >
        <Input
          placeholder="Ask a question"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="bg-white"
        />

        <Button
          className="mx-1.5"
          type="submit"
          disabled={!input.trim() || isPending}
        >
          {isPending ? (
            <Loader2Icon className="animate-spin h-5 w-5" />
          ) : (
            "Ask"
          )}
        </Button>
      </form>
    </div>
  );
};

export default Chat;
