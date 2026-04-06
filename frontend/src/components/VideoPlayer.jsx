import React from 'react';
import { Download, RefreshCw, Eye, Image as ImageIcon } from 'lucide-react';

export default function VideoPlayer({ url, thumbnailUrl, thumbnailVariants, metadata, onReset }) {
  if (!url) return null;

  const duration = typeof metadata?.duration_sec === 'number' ? metadata.duration_sec.toFixed(1) : 'Unknown';
  const resolution = metadata?.resolution || '1080x1920';
  const fileSize = metadata?.file_size_mb ?? 'Unknown';
  const score = metadata?.score ?? 'N/A';
  const retentionBreakdown = metadata?.retention_report?.breakdown || null;
  const retentionFlags = metadata?.retention_report?.flags || [];

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

      {thumbnailUrl && (
        <div className="w-full space-y-3">
          <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-3">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-300">
              <ImageIcon size={16} /> Thumbnail Preview
            </div>
            <img src={thumbnailUrl} alt="Generated thumbnail" className="w-full rounded-lg object-cover" />
          </div>
          <a
            href={thumbnailUrl}
            download="shorts_thumbnail.jpg"
            className="w-full bg-slate-700 hover:bg-slate-600 text-white font-bold py-3 px-4 rounded-lg transition-all flex justify-center items-center gap-2"
          >
            <Download size={18} /> Download Thumbnail
          </a>

          {!!thumbnailVariants?.length && (
            <div className="grid grid-cols-2 gap-3">
              {thumbnailVariants.map((variant) => (
                <a
                  key={variant.name}
                  href={variant.url}
                  download={`shorts_thumbnail_${variant.name}.jpg`}
                  className="rounded-xl border border-slate-700 bg-slate-900/60 p-2 transition hover:border-purple-400"
                >
                  <img src={variant.url} alt={variant.label} className="w-full rounded-lg object-cover" />
                  <div className="mt-2 text-xs font-semibold text-slate-300">{variant.label}</div>
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {metadata && (
        <div className="w-full bg-slate-900/50 p-4 rounded-lg border border-slate-700 space-y-3 text-sm">
          <h4 className="font-semibold text-slate-300 flex items-center gap-2 mb-3">
            <Eye size={16} /> Metadata
          </h4>
          <div className="flex justify-between text-slate-400">
            <span>Duration:</span>
            <span className="text-white">{duration === 'Unknown' ? duration : `${duration}s`}</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>Resolution:</span>
            <span className="text-white">{resolution}</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>File Size:</span>
            <span className="text-white">{typeof fileSize === 'number' ? `${fileSize} MB` : fileSize}</span>
          </div>
          <div className="flex justify-between text-slate-400">
            <span>Est. Viral Score:</span>
            <span className="text-green-400 font-bold">{score === 'N/A' ? score : `${score}/100 🚀`}</span>
          </div>

          {retentionBreakdown && (
            <div className="rounded-lg border border-slate-700 bg-slate-950/60 p-3 space-y-2">
              <div className="text-sm font-semibold text-white">Retention Breakdown</div>
              {Object.entries(retentionBreakdown).map(([key, value]) => (
                <div key={key} className="flex justify-between text-slate-400">
                  <span>{key.replaceAll('_', ' ')}</span>
                  <span className="text-white">{value}</span>
                </div>
              ))}
              {!!retentionFlags.length && (
                <div className="pt-2 space-y-1">
                  {retentionFlags.map((flag) => (
                    <div key={flag} className="text-amber-300 text-xs">{flag}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
