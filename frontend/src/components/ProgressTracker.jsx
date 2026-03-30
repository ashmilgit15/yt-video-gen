import React from 'react';
import { CheckCircle2, Loader2, Image as ImageIcon, Mic, Clapperboard, FileText } from 'lucide-react';

export default function ProgressTracker({ step, progress }) {
  const steps = [
    { id: 'script', label: 'Script Generated', icon: FileText },
    { id: 'assets', label: `Generating Assets (${progress.completed}/${progress.total})`, icon: ImageIcon },
    { id: 'video', label: 'Assembling Video...', icon: Clapperboard },
    { id: 'done', label: 'Done!', icon: CheckCircle2 }
  ];

  const getStatus = (stepId) => {
    if (step === stepId) return 'active';
    const index = steps.findIndex(s => s.id === stepId);
    const currentIndex = steps.findIndex(s => s.id === step);
    if (index < currentIndex || step === 'done') return 'completed';
    return 'pending';
  };

  return (
    <div className="max-w-xl mx-auto mt-8 bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-xl">
      <h3 className="text-xl font-bold mb-6 text-center text-white">Generation Progress</h3>
      
      <div className="space-y-6">
        {steps.map((s, i) => {
          const status = getStatus(s.id);
          const Icon = s.icon;
          
          return (
            <div key={s.id} className="relative">
              {i !== steps.length - 1 && (
                <div 
                  className={`absolute left-5 top-10 w-0.5 h-10 ${status === 'completed' ? 'bg-purple-500' : 'bg-slate-700'}`} 
                />
              )}
              
              <div className="flex items-center gap-4">
                <div className={`
                  w-10 h-10 rounded-full flex items-center justify-center border-2 z-10 bg-slate-800
                  ${status === 'completed' ? 'border-purple-500 text-purple-500' : 
                    status === 'active' ? 'border-blue-400 text-blue-400 shadow-[0_0_15px_rgba(96,165,250,0.5)]' : 
                    'border-slate-600 text-slate-500'}
                `}>
                  {status === 'active' ? (
                    <div className="animate-spin">
                      <Loader2 size={20} />
                    </div>
                  ) : status === 'completed' ? (
                    <CheckCircle2 size={20} />
                  ) : (
                    <Icon size={20} />
                  )}
                </div>
                
                <div className="flex-1">
                  <h4 className={`font-semibold ${status === 'pending' ? 'text-slate-500' : 'text-slate-200'}`}>
                    {s.label}
                  </h4>
                    {status === 'active' && s.id === 'assets' && (
                      <div className="w-full bg-slate-700 h-2 mt-2 rounded-full overflow-hidden">
                        <div 
                          className="bg-blue-400 h-full rounded-full"
                          style={{ width: `${progress.total ? (progress.completed / progress.total) * 100 : 0}%` }}
                        />
                      </div>
                    )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
