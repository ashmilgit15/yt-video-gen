import React from 'react';
import { Download, RefreshCw, Eye } from 'lucide-react';

export default function VideoPlayer({ url, metadata, onReset }) {
  if (!url) return null;

  return (
    <div className="mt-8 max-w-sm mx-auto space-y-6 flex flex-col items-center">
      <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-2xl relative w-full overflow-hidden" style={{ aspectRatio: '9/16' }}>
        <video 
          controls 
          autoPlay 
          loop 
          className="w-full h-full object-contain rounded-lg bg-black"
          src={url}
        />
      </div>

      <div className="flex gap-4 w-full">
        <a 
          href={url}
          download="shorts_video.mp4"
          className="flex-1 bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 px-4 rounded-lg transition-all flex justify-center items-center gap-2 shadow-[0_0_15px_rgba(168,85,247,0.4)]"
        >
          <Download size={20} /> Download MP4
        </a>
        
        <button 
          onClick={onReset}
          className="bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 px-4 rounded-lg transition-all flex justify-center items-center gap-2"
        >
          <RefreshCw size={20} /> New
        </button>
      </div>

      {metadata && (
        <div className="w-full bg-slate-900/50 p-4 rounded-lg border border-slate-700 space-y-2 text-sm">
          <h4 className="font-semibold text-slate-300 flex items-center gap-2 mb-3">
            <Eye size={16} /> Metadata
          </h4>
          <div className="flex justify-between text-slate-400">
            <span>Duration:</span>
            <span className="text-white">{metadata.duration_sec.toFixed(1)}s</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>Resolution:</span>
            <span className="text-white">{metadata.resolution}</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>File Size:</span>
            <span className="text-white">{metadata.file_size_mb} MB</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>Est. Viral Score:</span>
            <span className="text-green-400 font-bold">{metadata.score}/100 🚀</span>
          </div>
        </div>
      )}
    </div>
  );
}
