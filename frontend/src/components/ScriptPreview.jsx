import React from 'react';
import { RefreshCw, Play, Volume2 } from 'lucide-react';

export default function ScriptPreview({ script, setScript, onProceed }) {
  if (!script) return null;

  const handleNarrationChange = (index, value) => {
    const updated = [...script.scenes];
    updated[index].narration = value;
    setScript({ ...script, scenes: updated });
  };

  const handlePromptChange = (index, value) => {
    const updated = [...script.scenes];
    updated[index].image_prompt = value;
    setScript({ ...script, scenes: updated });
  };

  return (
    <div className="mt-8 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-xl font-bold text-white">Review Script: {script.title}</h3>
        <button 
          onClick={onProceed}
          className="bg-green-600 hover:bg-green-500 text-white font-bold py-2 px-6 rounded-lg transition-all flex items-center gap-2"
        >
          <Play size={18} /> Render Video
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {script.scenes.map((scene, index) => (
          <div key={index} className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-md">
            <div className="flex justify-between items-center mb-3">
              <span className="bg-purple-900 text-purple-200 text-xs font-bold px-2 py-1 rounded">
                Scene {scene.scene_number}
              </span>
            </div>
            
            <div className="mb-4">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-1">
                <Volume2 size={16} className="text-blue-400" /> Narration
              </label>
              <textarea
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-y min-h-[80px]"
                value={scene.narration}
                onChange={(e) => handleNarrationChange(index, e.target.value)}
              />
            </div>

            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-slate-300 mb-1">
                <RefreshCw size={16} className="text-pink-400" /> Image Prompt (9:16 Vertical)
              </label>
              <textarea
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm focus:ring-2 focus:ring-pink-500 outline-none resize-y min-h-[80px]"
                value={scene.image_prompt}
                onChange={(e) => handlePromptChange(index, e.target.value)}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
