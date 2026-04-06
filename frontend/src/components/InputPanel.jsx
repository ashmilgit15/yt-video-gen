import React, { useState } from 'react';
import { Wand2 } from 'lucide-react';

export default function InputPanel({ onSubmit, disabled }) {
  const [topic, setTopic] = useState('');
  const [style, setStyle] = useState('Cinematic Facts');
  const [duration, setDuration] = useState('30s');
  const [voice, setVoice] = useState('Sarah');

  const styleOptions = [
    'Cinematic Facts',
    'Educational',
    'Myth-Busting',
    'Story',
    'Fast-Paced Listicle',
    'Motivational',
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!topic.trim()) return;
    onSubmit({ topic, style, duration, voice });
  };

  return (
    <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-xl max-w-2xl mx-auto w-full">
      <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
        <Wand2 className="text-purple-400" /> YouTube Shorts Generator
      </h2>
      
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">What's your video about?</label>
          <input
            type="text"
            className="w-full bg-slate-900 border border-slate-600 rounded-lg px-4 py-3 text-white placeholder-slate-400 focus:ring-2 focus:ring-purple-500 focus:border-transparent outline-none transition"
            placeholder="10 facts about black holes"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={disabled}
            required
          />
          <p className="text-xs text-slate-400 mt-2">
            Built for hook-first scripts, cinematic visuals, animated captions, and stronger retention.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Style</label>
            <select
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:ring-2 focus:ring-purple-500 outline-none"
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              disabled={disabled}
            >
              {styleOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Duration (max 60s)</label>
            <select
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:ring-2 focus:ring-purple-500 outline-none"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              disabled={disabled}
            >
              <option value="15s">15 Seconds</option>
              <option value="30s">30 Seconds</option>
              <option value="45s">45 Seconds</option>
              <option value="60s">60 Seconds</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Voiceover</label>
            <select
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:ring-2 focus:ring-purple-500 outline-none"
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              disabled={disabled}
            >
              <option value="Sarah">Sarah (Female)</option>
              <option value="Bella">Bella (Female)</option>
              <option value="Aria">Aria (Female)</option>
            </select>
          </div>
        </div>

        <button
          type="submit"
          disabled={disabled || !topic.trim()}
          className="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 px-4 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-4"
        >
          {disabled ? 'Generating...' : 'Generate Script'}
        </button>
      </form>
    </div>
  );
}
