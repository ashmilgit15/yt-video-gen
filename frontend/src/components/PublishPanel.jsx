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
  channelPreviews,
  selectedAccountIds,
  uploads,
  connecting,
  uploading,
  metadata,
  thumbnailVariants,
  publishAt,
  privacyStatus,
  savingSelection,
  savingPresetId,
  refreshingMetadata,
  refreshingThumbnails,
  onToggleAccount,
  onConnect,
  onDisconnect,
  onPublishAtChange,
  onPrivacyStatusChange,
  onSaveChannelPreset,
  onSelectTitle,
  onSelectThumbnail,
  onUseSuggestedSchedule,
  onRegenerateMetadata,
  onRegenerateThumbnails,
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
            <div className="flex flex-wrap gap-3 items-center justify-between">
              <div>
                <div className="text-white font-semibold">Upload strategy</div>
                <p className="text-sm text-slate-400 mt-1">
                  Content-aware defaults are generated automatically from the finished script.
                </p>
              </div>

              <div className="min-w-[220px]">
                <label className="block text-sm font-medium text-slate-300 mb-1">Privacy</label>
                <select
                  value={privacyStatus}
                  onChange={(event) => onPrivacyStatusChange(event.target.value)}
                  className="w-full rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-white outline-none focus:border-purple-400"
                >
                  <option value="channel_default">Channel default</option>
                  <option value="private">Private</option>
                  <option value="unlisted">Unlisted</option>
                  <option value="public">Public</option>
                </select>
              </div>
            </div>

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

            {metadata && (
              <div className="rounded-xl border border-slate-700 bg-slate-950/60 p-4 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-purple-500/30 bg-purple-500/10 px-3 py-1 text-xs font-semibold text-purple-200">
                    Category: {metadata.category_label || metadata.category_id || 'People & Blogs'}
                  </span>
                  <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-200">
                    Suggested publish: {metadata.suggested_publish_mode || 'scheduled'}
                  </span>
                  <button
                    type="button"
                    onClick={onRegenerateMetadata}
                    disabled={refreshingMetadata}
                    className="rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold text-slate-200 transition hover:border-purple-400 disabled:opacity-60"
                  >
                    {refreshingMetadata ? 'Refreshing metadata...' : 'Refresh metadata ideas'}
                  </button>
                  <button
                    type="button"
                    onClick={onRegenerateThumbnails}
                    disabled={refreshingThumbnails}
                    className="rounded-full border border-slate-600 px-3 py-1 text-xs font-semibold text-slate-200 transition hover:border-purple-400 disabled:opacity-60"
                  >
                    {refreshingThumbnails ? 'Refreshing thumbnails...' : 'Refresh thumbnails'}
                  </button>
                </div>

                <div>
                  <div className="text-sm font-semibold text-white">Title</div>
                  <p className="mt-1 text-sm text-slate-300">{metadata.selected_title || metadata.title}</p>
                </div>

                <div>
                  <div className="text-sm font-semibold text-white">Description Preview</div>
                  <p className="mt-1 text-sm text-slate-400 whitespace-pre-wrap">
                    {metadata.description?.slice(0, 220)}
                    {metadata.description?.length > 220 ? '...' : ''}
                  </p>
                </div>

                {!!metadata.hashtags?.length && (
                  <div>
                    <div className="text-sm font-semibold text-white">Hashtags</div>
                    <p className="mt-1 text-sm text-purple-200">{metadata.hashtags.join(' ')}</p>
                  </div>
                )}

                {!!metadata.tags?.length && (
                  <div>
                    <div className="text-sm font-semibold text-white">Search Tags</div>
                    <p className="mt-1 text-sm text-slate-400">{metadata.tags.join(', ')}</p>
                  </div>
                )}

                {!!metadata.title_variants?.length && (
                  <div>
                    <div className="text-sm font-semibold text-white">Title Variants</div>
                    <div className="mt-2 space-y-2">
                      {metadata.title_variants.map((variant) => (
                        <div key={variant.title} className="rounded-lg border border-slate-700 bg-slate-900/70 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <div className="text-sm text-white">{variant.title}</div>
                              <div className="mt-1 text-xs text-slate-400">
                                {variant.angle} · score {variant.score}
                              </div>
                            </div>
                            <button
                              type="button"
                              onClick={() => onSelectTitle(variant.title)}
                              disabled={savingSelection}
                              className={`rounded-lg px-3 py-2 text-xs font-semibold transition ${metadata.selected_title === variant.title ? 'bg-emerald-600 text-white' : 'border border-slate-600 text-slate-200 hover:border-purple-400'}`}
                            >
                              {metadata.selected_title === variant.title ? 'Selected' : 'Use this'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {!!thumbnailVariants?.length && (
                  <div>
                    <div className="text-sm font-semibold text-white">Thumbnail Candidates</div>
                    <div className="mt-2 grid grid-cols-2 gap-3">
                      {thumbnailVariants.map((variant) => (
                        <div key={variant.name} className="rounded-lg border border-slate-700 bg-slate-900/70 p-2">
                          <img src={variant.url} alt={variant.label} className="w-full rounded-lg object-cover" />
                          <div className="mt-2 flex items-center justify-between gap-2">
                            <div className="text-xs text-slate-300">{variant.label}</div>
                            <button
                              type="button"
                              onClick={() => onSelectThumbnail(variant.name)}
                              disabled={savingSelection}
                              className={`rounded-lg px-2 py-1 text-xs font-semibold transition ${metadata.selected_thumbnail_variant === variant.name ? 'bg-emerald-600 text-white' : 'border border-slate-600 text-slate-200 hover:border-purple-400'}`}
                            >
                              {metadata.selected_thumbnail_variant === variant.name ? 'Selected' : 'Use'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {metadata.retention_report && (
                  <div>
                    <div className="text-sm font-semibold text-white">Retention Report</div>
                    <div className="mt-2 rounded-lg border border-slate-700 bg-slate-900/70 p-3 space-y-2">
                      <div className="text-emerald-300 font-semibold">
                        Overall score: {metadata.retention_report.overall_score}/100
                      </div>
                      {Object.entries(metadata.retention_report.breakdown || {}).map(([key, value]) => (
                        <div key={key} className="flex justify-between text-xs text-slate-400">
                          <span>{key.replaceAll('_', ' ')}</span>
                          <span className="text-white">{value}</span>
                        </div>
                      ))}
                      {!!metadata.retention_report.flags?.length && (
                        <div className="pt-2 space-y-1">
                          {metadata.retention_report.flags.map((flag) => (
                            <div key={flag} className="text-xs text-amber-300">{flag}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {accounts.map((account) => {
            const accountUploads = uploadsByAccount[account.id] || [];
            const latestUpload = accountUploads[0];
            const isSelected = selectedAccountIds.includes(account.id);
            const preview = channelPreviews[account.id];
            const preset = account.preset || {};
            const suggestedPublishAt =
              preview?.channel_schedule?.suggested_publish_at ??
              account.schedule_recommendation?.suggested_publish_at;
            const suggestedPublishLabel = suggestedPublishAt
              ? new Date(suggestedPublishAt).toLocaleString()
              : 'No suggestion yet';

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

                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 rounded-lg border border-slate-700 bg-slate-800/60 p-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Channel niche</label>
                    <select
                      value={preset.niche || 'general'}
                      onChange={(event) => onSaveChannelPreset(account.id, { niche: event.target.value })}
                      disabled={savingPresetId === account.id}
                      className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white"
                    >
                      <option value="general">General</option>
                      <option value="technology">Technology</option>
                      <option value="education">Education</option>
                      <option value="motivation">Motivation</option>
                      <option value="entertainment">Entertainment</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Content goal</label>
                    <select
                      value={preset.content_goal || 'subscriber_growth'}
                      onChange={(event) => onSaveChannelPreset(account.id, { content_goal: event.target.value })}
                      disabled={savingPresetId === account.id}
                      className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white"
                    >
                      <option value="subscriber_growth">Subscriber growth</option>
                      <option value="reach">Reach</option>
                      <option value="authority">Authority</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Default category</label>
                    <select
                      value={preset.default_category_id || '22'}
                      onChange={(event) => onSaveChannelPreset(account.id, { default_category_id: event.target.value })}
                      disabled={savingPresetId === account.id}
                      className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white"
                    >
                      <option value="22">People & Blogs</option>
                      <option value="24">Entertainment</option>
                      <option value="26">Howto & Style</option>
                      <option value="27">Education</option>
                      <option value="28">Science & Technology</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Preferred hour</label>
                    <input
                      type="number"
                      min="0"
                      max="23"
                      value={preset.preferred_hour ?? 19}
                      onChange={(event) => onSaveChannelPreset(account.id, { preferred_hour: Number(event.target.value) })}
                      disabled={savingPresetId === account.id}
                      className="w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white"
                    />
                  </div>

                  <div className="md:col-span-2 rounded-lg border border-slate-700 bg-slate-900/70 p-3 space-y-2">
                    <div className="text-xs font-semibold text-slate-300">Per-channel upload preview</div>
                    <div className="text-sm text-white">{preview?.selected_title || metadata?.selected_title || metadata?.title}</div>
                    <div className="text-xs text-slate-400">
                      {(preview?.hashtags || []).join(' ')}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
                      <span>Suggested slot:</span>
                      <span className="text-emerald-300">{suggestedPublishLabel}</span>
                      <button
                        type="button"
                        onClick={() => onUseSuggestedSchedule(account.id)}
                        className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-200 hover:border-purple-400"
                      >
                        Use suggested slot
                      </button>
                    </div>
                    <div className="text-xs text-slate-500">
                      {preview?.channel_schedule?.reason || account.schedule_recommendation?.reason}
                    </div>
                  </div>
                </div>
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
