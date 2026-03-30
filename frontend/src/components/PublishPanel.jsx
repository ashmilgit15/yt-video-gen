import React from 'react';
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Link2,
  Loader2,
  RotateCcw,
  Trash2,
  Upload,
} from 'lucide-react';


const ACTIVE_UPLOAD_STATUSES = new Set(['queued', 'uploading', 'retry_scheduled']);


function statusBadge(status) {
  if (status === 'completed') {
    return 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30';
  }
  if (status === 'retry_scheduled') {
    return 'bg-amber-500/15 text-amber-300 border border-amber-500/30';
  }
  if (ACTIVE_UPLOAD_STATUSES.has(status)) {
    return 'bg-blue-500/15 text-blue-300 border border-blue-500/30';
  }
  if (status === 'failed') {
    return 'bg-red-500/15 text-red-300 border border-red-500/30';
  }
  return 'bg-slate-700 text-slate-300 border border-slate-600';
}


export default function PublishPanel({
  accounts,
  selectedAccountIds,
  uploads,
  connecting,
  uploading,
  publishAt,
  onToggleAccount,
  onConnect,
  onDisconnect,
  onPublishAtChange,
  onUpload,
  onRetryUpload,
}) {
  const uploadsByAccount = uploads.reduce((acc, upload) => {
    const accountId = upload.youtube_account?.id;
    if (!accountId) {
      return acc;
    }

    if (!acc[accountId]) {
      acc[accountId] = [];
    }

    acc[accountId].push(upload);
    return acc;
  }, {});

  return (
    <div className="w-full max-w-4xl mx-auto bg-slate-800/80 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h3 className="text-2xl font-bold text-white">Publish to YouTube</h3>
          <p className="text-slate-400 mt-2 max-w-2xl">
            Upload this Short to one or more connected channels. Title, description, and tags are generated automatically from the final script.
          </p>
        </div>

        <button
          type="button"
          onClick={onConnect}
          disabled={connecting}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-purple-600 px-4 py-3 font-semibold text-white transition hover:bg-purple-500 disabled:opacity-60"
        >
          {connecting ? <Loader2 className="animate-spin" size={18} /> : <Link2 size={18} />}
          {connecting ? 'Connecting...' : 'Connect YouTube Account'}
        </button>
      </div>

      {!accounts.length && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-100 flex items-start gap-3">
          <AlertTriangle size={20} className="mt-0.5 text-amber-300" />
          <p>
            No YouTube accounts are connected yet. Connect at least one account to upload this Short.
          </p>
        </div>
      )}

      {!!accounts.length && (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-700 bg-slate-900/70 p-4 space-y-3">
            <div className="flex items-center gap-2 text-white font-semibold">
              <CalendarClock size={18} className="text-purple-300" />
              Scheduled publishing
            </div>
            <p className="text-sm text-slate-400">
              Leave this empty for an immediate upload. If you choose a future time, the video is uploaded now and YouTube publishes it automatically at that time.
            </p>
            <input
              type="datetime-local"
              value={publishAt}
              onChange={(event) => onPublishAtChange(event.target.value)}
              className="w-full max-w-sm rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white outline-none focus:border-purple-400"
            />
          </div>

          {accounts.map((account) => {
            const accountUploads = uploadsByAccount[account.id] || [];
            const latestUpload = accountUploads[0];
            const isSelected = selectedAccountIds.includes(account.id);

            return (
              <div
                key={account.id}
                className="rounded-xl border border-slate-700 bg-slate-900/70 p-4"
              >
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <label className="flex items-center gap-4 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleAccount(account.id)}
                      className="h-5 w-5 rounded border-slate-500 bg-slate-800 text-purple-500"
                    />

                    <div className="flex items-center gap-3">
                      {account.thumbnail_url ? (
                        <img
                          src={account.thumbnail_url}
                          alt={account.channel_title}
                          className="h-12 w-12 rounded-full object-cover border border-slate-600"
                        />
                      ) : (
                        <div className="h-12 w-12 rounded-full bg-slate-700 border border-slate-600" />
                      )}

                      <div>
                        <div className="font-semibold text-white">{account.channel_title}</div>
                        <div className="text-xs text-slate-400">Channel ID: {account.channel_id}</div>
                      </div>
                    </div>
                  </label>

                  <div className="flex items-center gap-3">
                    {latestUpload && (
                      <span className={`text-xs px-2.5 py-1 rounded-full ${statusBadge(latestUpload.status)}`}>
                        {latestUpload.status}
                      </span>
                    )}

                    <button
                      type="button"
                      onClick={() => onDisconnect(account.id)}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-600 px-3 py-2 text-slate-300 transition hover:border-red-400 hover:text-red-300"
                    >
                      <Trash2 size={16} /> Disconnect
                    </button>
                  </div>
                </div>

                {latestUpload && (
                  <div className="mt-4 rounded-lg border border-slate-700 bg-slate-800/70 p-3 text-sm text-slate-300 space-y-2">
                    <div className="flex items-center gap-2 text-white font-medium">
                    {latestUpload.status === 'completed' ? (
                      <CheckCircle2 size={16} className="text-emerald-400" />
                    ) : latestUpload.status === 'failed' ? (
                      <AlertTriangle size={16} className="text-red-400" />
                    ) : latestUpload.status === 'retry_scheduled' ? (
                      <CalendarClock size={16} className="text-amber-400" />
                    ) : (
                      <Loader2 size={16} className="animate-spin text-blue-400" />
                    )}
                      Latest upload
                    </div>

                    <p className="text-slate-400">{latestUpload.title}</p>

                    {latestUpload.publish_at && (
                      <p className="text-slate-400">
                        Scheduled publish: {new Date(latestUpload.publish_at).toLocaleString()}
                      </p>
                    )}

                    {latestUpload.status === 'retry_scheduled' && latestUpload.next_retry_at && (
                      <p className="text-amber-300">
                        Retry queued for {new Date(latestUpload.next_retry_at).toLocaleString()}
                      </p>
                    )}

                    {latestUpload.youtube_url && (
                      <a
                        href={latestUpload.youtube_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex text-purple-300 hover:text-purple-200"
                      >
                        Open on YouTube
                      </a>
                    )}

                    {latestUpload.error_message && (
                      <p className="text-red-300">{latestUpload.error_message}</p>
                    )}

                    {(latestUpload.status === 'failed' || latestUpload.status === 'retry_scheduled') && (
                      <button
                        type="button"
                        onClick={() => onRetryUpload(latestUpload.id)}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-600 px-3 py-2 text-slate-200 transition hover:border-purple-400 hover:text-purple-200"
                      >
                        <RotateCcw size={16} /> Retry upload
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          <button
            type="button"
            onClick={onUpload}
            disabled={!selectedAccountIds.length || uploading}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 font-semibold text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {uploading ? <Loader2 className="animate-spin" size={18} /> : <Upload size={18} />}
            {uploading ? 'Queueing uploads...' : `Upload to ${selectedAccountIds.length || 0} Selected Account${selectedAccountIds.length === 1 ? '' : 's'}`}
          </button>
        </div>
      )}
    </div>
  );
}
