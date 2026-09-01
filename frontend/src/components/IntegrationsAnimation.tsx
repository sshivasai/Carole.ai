"use client";

import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mail, Video, Bot, Globe, Network, Database, Share2, RefreshCw, AppWindow } from "lucide-react";

const INTEGRATIONS = [
  { name: "OpenAI", id: "openai", svg: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M22.28 9.82a6 6 0 0 0-1.25-4.22A6 6 0 0 0 16 3.5a6 6 0 0 0-5 2.5 6 6 0 0 0-5-2.5 6 6 0 0 0-5.03 2.1 6 6 0 0 0-1.25 4.22 6 6 0 0 0 1.25 4.22A6 6 0 0 0 6 16.14a6 6 0 0 0 5 2.5 6 6 0 0 0 5-2.5 6 6 0 0 0 5-2.5A6 6 0 0 0 22.28 9.82z" /></svg>` },
  { name: "Gemini", id: "gemini", svg: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.666 0c.264 4.27 2.146 6.305 6.002 6.574-3.856.269-5.738 2.304-6.002 6.574-.264-4.27-2.146-6.305-6.002-6.574 3.856-.269 5.738-2.304 6.002-6.574zm7.668 11.233c.18 2.913 1.465 4.3 4.094 4.484-2.629.184-3.914 1.571-4.094 4.484-.18-2.913-1.465-4.3-4.094-4.484 2.629-.184 3.914-1.571 4.094-4.484z" /></svg>` },
  { name: "Tavily", id: "tavily", svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="4" /></svg>` },
  { name: "Browserbase", id: "browserbase", svg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line></svg>` },
  { name: "NVIDIA", id: "nvidia", svg: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M15.4 0H24v24h-8.6V0zM0 8.6h8.6V24H0V8.6zm24 15.4H0v-8.6h24v8.6z" /></svg>` },
  { name: "OpenRouter", id: "openrouter", icon: Network },
  { name: "Ollama", id: "ollama", icon: Bot },
  { name: "Scraper API", id: "scraper", icon: Globe },
  { name: "Gmail", id: "gmail", icon: Mail },
  { name: "GMeet", id: "gmeet", icon: Video },
  { name: "Playwright", id: "playwright", icon: AppWindow },
  { name: "Vector DB", id: "vectordb", icon: Database },
  { name: "GraphRAG", id: "rag", icon: Share2 },
  { name: "ReAct Loop", id: "react", icon: RefreshCw },
];

const WORKFLOWS = [
  {
    objective: "Scraped and aggregated competitor pricing data across 14 web portals.",
    activeTools: ["playwright", "scraper", "tavily", "openai"]
  },
  {
    objective: "Refactored legacy Python microservice and deployed to production.",
    activeTools: ["react", "openrouter", "nvidia", "openai"]
  },
  {
    objective: "Generated marketing copy, generated assets, and drafted email campaigns.",
    activeTools: ["gemini", "rag", "gmail", "gmeet"]
  },
  {
    objective: "Analyzed 200-page PDF financial report and extracted key metrics.",
    activeTools: ["ollama", "vectordb", "rag", "openai"]
  }
];

export default function IntegrationsAnimation() {
  const [workflowIdx, setWorkflowIdx] = useState(0);
  const [isBlinking, setIsBlinking] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setWorkflowIdx((idx) => (idx + 1) % WORKFLOWS.length);
    }, 4500); // switch workflow every 4.5s
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Random blinking logic
    const blink = () => {
      setIsBlinking(true);
      setTimeout(() => setIsBlinking(false), 150); // fast blink
      
      // Schedule next blink randomly between 2s and 6s
      const nextBlink = Math.random() * 4000 + 2000;
      setTimeout(blink, nextBlink);
    };
    
    const timeout = setTimeout(blink, 2000);
    return () => clearTimeout(timeout);
  }, []);

  const currentWorkflow = WORKFLOWS[workflowIdx];

  // Layout constants
  const CANVAS_W = 480;
  const CANVAS_H = 460;
  
  const AGENT_X = CANVAS_W / 2;
  const AGENT_Y = 50;
  
  const OBJECTIVE_X = CANVAS_W / 2;
  const OBJECTIVE_Y = 400;

  const TOOL_Y = 220;

  return (
    <div style={{ position: "relative", width: CANVAS_W, height: CANVAS_H, margin: "0 auto", overflow: "visible", fontFamily: "'Google Sans Flex', sans-serif" }}>
      
      {/* SVG Background Lines */}
      <svg style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", zIndex: 0, overflow: "visible" }}>
        {[0, 1, 2, 3].map((i) => {
          const x = 96 + i * 96;
          const strokeColor = "rgba(167, 139, 250, 0.4)";
          const strokeWidth = 2;
          
          return (
            <g key={`flow-${i}`}>
              {/* Agent -> Tool */}
              <motion.path 
                d={`M ${AGENT_X} ${AGENT_Y + 36} C ${AGENT_X} ${TOOL_Y - 60}, ${x} ${AGENT_Y + 60}, ${x} ${TOOL_Y - 36}`} 
                fill="none" 
                stroke={strokeColor} 
                strokeWidth={strokeWidth}
                animate={{ stroke: strokeColor }}
                transition={{ duration: 0.5 }}
              />
              {/* Tool -> Objective */}
              <motion.path 
                d={`M ${x} ${TOOL_Y + 36} C ${x} ${TOOL_Y + 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 50}`} 
                fill="none" 
                stroke={strokeColor} 
                strokeWidth={strokeWidth}
                animate={{ stroke: strokeColor }}
                transition={{ duration: 0.5 }}
              />

              {/* Animated Flow Pulses for All Tools */}
              <>
                <motion.circle
                  r={3}
                  fill="#a78bfa"
                  initial={{ offsetDistance: "0%", opacity: 0 }}
                  animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "linear", delay: i * 0.2 }}
                  style={{ 
                    filter: "drop-shadow(0 0 4px #a78bfa)",
                    offsetPath: `path('M ${AGENT_X} ${AGENT_Y + 36} C ${AGENT_X} ${TOOL_Y - 60}, ${x} ${AGENT_Y + 60}, ${x} ${TOOL_Y - 36}')` 
                  } as any}
                />
                <motion.circle
                  r={3}
                  fill="#10b981"
                  initial={{ offsetDistance: "0%", opacity: 0 }}
                  animate={{ offsetDistance: "100%", opacity: [0, 1, 1, 0] }}
                  transition={{ duration: 1.5, repeat: Infinity, ease: "linear", delay: i * 0.2 + 0.75 }}
                  style={{ 
                    filter: "drop-shadow(0 0 4px #10b981)",
                    offsetPath: `path('M ${x} ${TOOL_Y + 36} C ${x} ${TOOL_Y + 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 80}, ${OBJECTIVE_X} ${OBJECTIVE_Y - 50}')` 
                  } as any}
                />
              </>
            </g>
          );
        })}
      </svg>

      {/* Top Node: Agent Brain (Animated Face) */}
      <motion.div 
        style={{ 
          position: "absolute", left: AGENT_X - 40, top: AGENT_Y - 40,
          width: 80, height: 80, borderRadius: "50%", background: "rgba(167, 139, 250, 0.1)", 
          border: "1px solid rgba(167, 139, 250, 0.3)", display: "flex", alignItems: "center", justifyContent: "center", 
          zIndex: 10, overflow: "visible" 
        }}
        animate={{ y: [0, -5, 0], boxShadow: ["0 0 20px rgba(167,139,250,0.2)", "0 0 40px rgba(167,139,250,0.4)", "0 0 20px rgba(167,139,250,0.2)"] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      >
        <motion.div
          animate={{ scale: [1, 1.05, 1], filter: ["drop-shadow(0 0 10px rgba(167,139,250,0.2))", "drop-shadow(0 0 25px rgba(167,139,250,0.5))", "drop-shadow(0 0 10px rgba(167,139,250,0.2))"] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          style={{ width: "90%", height: "90%", position: "relative" }}
        >
          <img 
            src={isBlinking ? "/branding/agent-eyes-closed.png" : "/branding/agent-eyes-open.png"} 
            alt="Carole Agent" 
            style={{ width: "100%", height: "100%", objectFit: "contain", borderRadius: "50%" }} 
          />
        </motion.div>
      </motion.div>

      {/* Middle Nodes: 4 Dynamic Tools */}
      {[0, 1, 2, 3].map((i) => {
        const toolId = currentWorkflow.activeTools[i];
        const tool = INTEGRATIONS.find(t => t.id === toolId)!;
        const Icon = tool.icon;
        const x = 96 + i * 96;
        const y = TOOL_Y;
        
        return (
          <div key={`slot-${i}`} style={{ position: "absolute", left: x - 40, top: y - 40, display: "flex", flexDirection: "column", alignItems: "center", gap: "12px", width: 80, zIndex: 10 }}>
            <AnimatePresence mode="popLayout">
              <motion.div 
                key={tool.id}
                initial={{ scale: 0.8, opacity: 0, rotateY: 90 }}
                animate={{ scale: 1, opacity: 1, rotateY: 0 }}
                exit={{ scale: 0.8, opacity: 0, rotateY: -90, position: "absolute" }}
                transition={{ duration: 0.4 }}
                style={{ 
                  width: 64, height: 64, borderRadius: "16px", background: "rgba(255, 255, 255, 0.05)", 
                  border: "1px solid rgba(167, 139, 250, 0.5)", display: "flex", alignItems: "center", justifyContent: "center",
                  boxShadow: "0 0 15px rgba(167, 139, 250, 0.2)",
                  backdropFilter: "blur(8px)"
                }}
              >
                {tool.svg ? (
                  <div style={{ width: 28, height: 28, color: "#9ca3af" }} dangerouslySetInnerHTML={{ __html: tool.svg }} />
                ) : Icon ? (
                  <Icon size={28} color="#9ca3af" strokeWidth={1.5} />
                ) : null}
              </motion.div>
            </AnimatePresence>
            
            <AnimatePresence mode="popLayout">
              <motion.span 
                key={tool.id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5, position: "absolute" }}
                transition={{ duration: 0.4 }}
                style={{ fontSize: 11, fontWeight: 500, color: "#9ca3af", letterSpacing: "0.02em", textAlign: "center" }}
              >
                {tool.name}
              </motion.span>
            </AnimatePresence>
          </div>
        );
      })}

      {/* Bottom Node: Actual Work Accomplished */}
      <motion.div 
        style={{ 
          position: "absolute", left: OBJECTIVE_X - 220, top: OBJECTIVE_Y - 50,
          background: "rgba(0,0,0,0.7)", border: "1px solid rgba(167, 139, 250, 0.4)", borderRadius: 16, 
          padding: "24px", width: "440px", display: "flex", flexDirection: "column", gap: 12, zIndex: 10, backdropFilter: "blur(16px)",
          boxShadow: "0 8px 32px rgba(167, 139, 250, 0.15)"
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#10b981", boxShadow: "0 0 10px #10b981" }} />
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "rgba(255,255,255,0.5)", textTransform: "uppercase" }}>Team Objective Complete</span>
        </div>
        
        <div style={{ height: "48px", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <AnimatePresence mode="wait">
            <motion.p
              key={workflowIdx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.4 }}
              style={{ margin: 0, fontSize: 14, lineHeight: "24px", fontWeight: 500, color: "#9ca3af", textAlign: "center" }}
            >
              {currentWorkflow.objective}
            </motion.p>
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
