import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
  useAuth,
} from '@clerk/react';
import InputPanel from './components/InputPanel';
import ScriptPreview from './components/ScriptPreview';
import ProgressTracker from './components/ProgressTracker';
import VideoPlayer from './components/VideoPlayer';
import PublishPanel from './components/PublishPanel';
import {
  configureApiAuth,
  disconnectYoutubeAccount,
  downloadThumbnail,
  downloadThumbnailVariant,
  downloadVideo,
  generateScript,
  getApiOrigin,
  getChannelPreview,
  getCurrentUser,
  getVideo,
  getYoutubeAccounts,
  regenerateThumbnailVariants,
  regenerateUploadMetadata,
  renderVideo,
  retryUpload,
  startYoutubeConnect,
  updateYoutubeAccountPreset,
  updatePublishSelection,
  uploadVideoToYoutube,
} from './api';
import './App.css';


const ACTIVE_UPLOAD_STATUSES = new Set(['queued', 'uploading', 'retry_scheduled']);


function App() {
  const { getToken, isLoaded, userId } = useAuth();

  const [step, setStep] = useState('input');
  const [loading, setLoading] = useState(false);
  const [syncingUser, setSyncingUser] = useState(false);
  const [connectingAccount, setConnectingAccount] = useState(false);
  const [queueingUpload, setQueueingUpload] = useState(false);
  const [error, setError] = useState('');

  const [script, setScript] = useState(null);
  const [videoConfig, setVideoConfig] = useState(null);
  const [videoId, setVideoId] = useState('');
  const [progress, setProgress] = useState({ completed: 0, total: 0 });
  const [videoData, setVideoData] = useState(null);
  const [videoUrl, setVideoUrl] = useState('');
  const [thumbnailUrl, setThumbnailUrl] = useState('');
  const [thumbnailVariants, setThumbnailVariants] = useState([]);
  const [youtubeAccounts, setYoutubeAccounts] = useState([]);
  const [channelPreviews, setChannelPreviews] = useState({});
  const [selectedAccountIds, setSelectedAccountIds] = useState([]);
  const [publishAt, setPublishAt] = useState('');
  const [privacyStatus, setPrivacyStatus] = useState('channel_default');
  const [savingSelection, setSavingSelection] = useState(false);
  const [savingPresetId, setSavingPresetId] = useState('');
  const [refreshingMetadata, setRefreshingMetadata] = useState(false);
  const [refreshingThumbnails, setRefreshingThumbnails] = useState(false);

  const activeUploads = useMemo(
    () => (videoData?.uploads || []).filter((upload) => ACTIVE_UPLOAD_STATUSES.has(upload.status)),
    [videoData],
  );

  const popupRef = useRef(null);

  useEffect(() => {
    if (!isLoaded) {
      configureApiAuth(null);
      return;
    }

    if (!userId) {
      configureApiAuth(null);
      return;
    }

    configureApiAuth(() => getToken());
  }, [getToken, isLoaded, userId]);

  useEffect(() => {
    if (!isLoaded || !userId) {
      setYoutubeAccounts([]);
      setSelectedAccountIds([]);
      return;
    }

    const bootstrap = async () => {
      setSyncingUser(true);
      try {
        await Promise.all([getCurrentUser(), refreshYoutubeAccounts()]);
      } catch (bootstrapError) {
        setError(bootstrapError?.response?.data?.detail || 'Failed to initialize your account.');
      } finally {
        setSyncingUser(false);
      }
    };

    bootstrap();
  }, [isLoaded, userId]);

  useEffect(() => {
    const handleMessage = (event) => {
      if (event.origin !== getApiOrigin()) {
        return;
      }

      if (event.data?.type !== 'youtube-connected') {
        return;
      }

      setConnectingAccount(false);
      if (event.data.success) {
        refreshYoutubeAccounts();
      } else {
        setError(event.data.message || 'Failed to connect the YouTube account.');
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

  useEffect(() => {
    if (!isLoaded || !userId || !videoId || step !== 'generating' && activeUploads.length === 0) {
      return;
    }

    let cancelled = false;
    let timeoutId = null;

    const poll = async () => {
      try {
        const currentVideo = await getVideo(videoId);
        if (cancelled) {
          return;
        }

        setVideoData(currentVideo);
        setProgress(currentVideo.progress);

        if (currentVideo.script) {
          setScript(currentVideo.script);
        }

        if (currentVideo.render_status === 'completed') {
          setStep('done');
          return;
        }

        if (currentVideo.render_status === 'failed') {
          setError(currentVideo.error_message || 'Video rendering failed.');
          setStep('script_review');
          return;
        }
      } catch (pollError) {
        if (cancelled) {
          return;
        }

        if (pollError?.response?.status !== 401 && pollError?.message !== 'Authentication token is not ready.') {
          console.error('Polling error', pollError);
        }
      }

      if (!cancelled) {
        timeoutId = window.setTimeout(poll, 2000);
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [activeUploads.length, isLoaded, step, userId, videoId]);

  useEffect(() => {
    if (step !== 'done' || !videoId || videoUrl) {
      return;
    }

    let cancelled = false;

    const loadVideoBlob = async () => {
      try {
        const blobUrl = await downloadVideo(videoId);
        if (cancelled) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        setVideoUrl(blobUrl);
      } catch (downloadError) {
        setError(downloadError?.response?.data?.detail || 'Failed to load the rendered video.');
      }
    };

    loadVideoBlob();

    return () => {
      cancelled = true;
    };
  }, [step, videoId, videoUrl]);

  useEffect(() => {
    if (step !== 'done' || !videoId || thumbnailUrl || !videoData?.metadata?.thumbnail_available) {
      return;
    }

    let cancelled = false;

    const loadThumbnailBlob = async () => {
      try {
        const blobUrl = await downloadThumbnail(videoId);
        if (cancelled) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        setThumbnailUrl(blobUrl);
      } catch {
        // Thumbnail is optional; keep the rest of the UI usable.
      }
    };

    loadThumbnailBlob();

    return () => {
      cancelled = true;
    };
  }, [step, thumbnailUrl, videoData, videoId]);

  useEffect(() => {
    if (step !== 'done' || !videoId || thumbnailVariants.length || !videoData?.metadata?.thumbnail_variants?.length) {
      return;
    }

    let cancelled = false;

    const loadThumbnailVariants = async () => {
      try {
        const variants = await Promise.all(
          videoData.metadata.thumbnail_variants.map(async (variant) => ({
            ...variant,
            url: await downloadThumbnailVariant(videoId, variant.name),
          })),
        );

        if (cancelled) {
          variants.forEach((variant) => URL.revokeObjectURL(variant.url));
          return;
        }

        setThumbnailVariants(variants);
      } catch {
        // Optional enhancement; ignore failures.
      }
    };

    loadThumbnailVariants();

    return () => {
      cancelled = true;
    };
  }, [step, thumbnailVariants.length, videoData, videoId]);

  useEffect(() => {
    const suggestedPrivacy = videoData?.upload_metadata?.suggested_privacy_status;
    if (suggestedPrivacy && privacyStatus !== 'channel_default') {
      setPrivacyStatus(suggestedPrivacy);
    }
  }, [privacyStatus, videoData?.upload_metadata?.suggested_privacy_status]);

  const refreshYoutubeAccounts = async () => {
    const data = await getYoutubeAccounts();
    setYoutubeAccounts(data.accounts || []);
    setSelectedAccountIds((current) =>
      current.filter((accountId) => (data.accounts || []).some((account) => account.id === accountId)),
    );
  };

  useEffect(() => {
    if (!videoId || !selectedAccountIds.length || !videoData?.upload_metadata) {
      setChannelPreviews({});
      return;
    }

    let cancelled = false;

    const loadPreviews = async () => {
      try {
        const previewEntries = await Promise.all(
          selectedAccountIds.map(async (accountId) => [accountId, await getChannelPreview(videoId, accountId)]),
        );
        if (!cancelled) {
          setChannelPreviews(Object.fromEntries(previewEntries));
        }
      } catch {
        if (!cancelled) {
          setChannelPreviews({});
        }
      }
    };

    loadPreviews();

    return () => {
      cancelled = true;
    };
  }, [selectedAccountIds, videoData?.upload_metadata, videoId]);

  const handleSaveChannelPreset = async (accountId, preset) => {
    setSavingPresetId(accountId);
    setError('');
    try {
      const updatedAccount = await updateYoutubeAccountPreset(accountId, preset);
      setYoutubeAccounts((current) => current.map((account) => (account.id === accountId ? updatedAccount : account)));
      if (videoId && videoData?.upload_metadata) {
        const preview = await getChannelPreview(videoId, accountId);
        setChannelPreviews((current) => ({ ...current, [accountId]: preview }));
      }
    } catch (presetError) {
      setError(presetError?.response?.data?.detail || 'Failed to save channel preset.');
    } finally {
      setSavingPresetId('');
    }
  };

  const handleUseSuggestedSchedule = (accountId) => {
    const suggestion = channelPreviews[accountId]?.channel_schedule?.suggested_publish_at
      || youtubeAccounts.find((account) => account.id === accountId)?.schedule_recommendation?.suggested_publish_at;
    if (!suggestion) {
      return;
    }
    const localValue = new Date(suggestion);
    const offsetMs = localValue.getTimezoneOffset() * 60 * 1000;
    const normalized = new Date(localValue.getTime() - offsetMs).toISOString().slice(0, 16);
    setPublishAt(normalized);
  };

  const handleGenerateScript = async (config) => {
    setLoading(true);
    setError('');
    setVideoConfig(config);
    try {
      const data = await generateScript(config.topic, config.style, config.duration);
      setVideoId(data.video_id);
      setScript({ title: data.title, scenes: data.scenes });
      setStep('script_review');
    } catch (error) {
      setError(error?.response?.data?.detail || 'Failed to generate script.');
    } finally {
      setLoading(false);
    }
  };

  const handleProceedToGeneration = async () => {
    if (!videoId || !script || !videoConfig) {
      return;
    }

    setStep('generating');
    setError('');
    setVideoUrl('');
    resetThumbnailObjects();
    setProgress({ completed: 0, total: script.scenes.length * 2 });

    try {
      const result = await renderVideo(videoId, script, videoConfig.voice);
      setVideoData(result);
    } catch (error) {
      setError(error?.response?.data?.detail || 'Failed to start video rendering.');
      setStep('script_review');
    }
  };

  const handleConnectYoutube = async () => {
    setConnectingAccount(true);
    setError('');

    try {
      const { auth_url: authUrl } = await startYoutubeConnect();
      popupRef.current = window.open(
        authUrl,
        'youtube-connect',
        'width=640,height=720,menubar=no,toolbar=no,status=no',
      );
    } catch (connectError) {
      setConnectingAccount(false);
      setError(connectError?.response?.data?.detail || 'Failed to start Google OAuth.');
    }
  };

  const handleDisconnectYoutube = async (accountId) => {
    try {
      await disconnectYoutubeAccount(accountId);
      await refreshYoutubeAccounts();
      setSelectedAccountIds((current) => current.filter((id) => id !== accountId));
    } catch (disconnectError) {
      setError(disconnectError?.response?.data?.detail || 'Failed to disconnect the YouTube account.');
    }
  };

  const handleToggleAccount = (accountId) => {
    setSelectedAccountIds((current) =>
      current.includes(accountId)
        ? current.filter((id) => id !== accountId)
        : [...current, accountId],
    );
  };

  const handleUploadVideo = async () => {
    if (!videoId || !selectedAccountIds.length) {
      return;
    }

    setQueueingUpload(true);
    setError('');

    try {
      const publishAtIso = publishAt ? new Date(publishAt).toISOString() : null;
      const data = await uploadVideoToYoutube(videoId, selectedAccountIds, privacyStatus, publishAtIso);
      setVideoData((current) => ({
        ...(current || {}),
        uploads: [...(current?.uploads || []), ...(data.uploads || [])],
      }));
    } catch (uploadError) {
      setError(uploadError?.response?.data?.detail || 'Failed to queue uploads.');
    } finally {
      setQueueingUpload(false);
    }
  };

  const handleRetryUpload = async (uploadId) => {
    try {
      const retriedUpload = await retryUpload(uploadId);
      setVideoData((current) => {
        if (!current) {
          return current;
        }

        const nextUploads = (current.uploads || []).map((upload) =>
          upload.id === uploadId ? retriedUpload : upload,
        );

        return {
          ...current,
          uploads: nextUploads,
        };
      });
    } catch (retryError) {
      setError(retryError?.response?.data?.detail || 'Failed to retry the upload.');
    }
  };

  const resetThumbnailObjects = () => {
    if (thumbnailUrl) {
      URL.revokeObjectURL(thumbnailUrl);
    }

    thumbnailVariants.forEach((variant) => {
      if (variant.url) {
        URL.revokeObjectURL(variant.url);
      }
    });

    setThumbnailUrl('');
    setThumbnailVariants([]);
  };

  const handleSelectTitle = async (selectedTitle) => {
    if (!videoId || !selectedTitle) {
      return;
    }

    setSavingSelection(true);
    setError('');
    try {
      const updatedVideo = await updatePublishSelection(videoId, { selected_title: selectedTitle });
      setVideoData(updatedVideo);
    } catch (selectionError) {
      setError(selectionError?.response?.data?.detail || 'Failed to save the selected title.');
    } finally {
      setSavingSelection(false);
    }
  };

  const handleSelectThumbnail = async (variantName) => {
    if (!videoId || !variantName) {
      return;
    }

    setSavingSelection(true);
    setError('');
    try {
      const updatedVideo = await updatePublishSelection(videoId, { selected_thumbnail_variant: variantName });
      setVideoData(updatedVideo);
      const chosenVariant = thumbnailVariants.find((variant) => variant.name === variantName);
      if (chosenVariant?.url) {
        if (thumbnailUrl && thumbnailUrl !== chosenVariant.url) {
          URL.revokeObjectURL(thumbnailUrl);
        }
        setThumbnailUrl(chosenVariant.url);
      }
    } catch (selectionError) {
      setError(selectionError?.response?.data?.detail || 'Failed to save the selected thumbnail.');
    } finally {
      setSavingSelection(false);
    }
  };

  const handleRegenerateMetadata = async () => {
    if (!videoId) {
      return;
    }

    setRefreshingMetadata(true);
    setError('');
    try {
      const updatedVideo = await regenerateUploadMetadata(videoId);
      setVideoData(updatedVideo);
    } catch (metadataError) {
      setError(metadataError?.response?.data?.detail || 'Failed to regenerate metadata.');
    } finally {
      setRefreshingMetadata(false);
    }
  };

  const handleRegenerateThumbnails = async () => {
    if (!videoId) {
      return;
    }

    setRefreshingThumbnails(true);
    setError('');
    try {
      resetThumbnailObjects();
      const updatedVideo = await regenerateThumbnailVariants(videoId);
      setVideoData(updatedVideo);
    } catch (thumbnailError) {
      setError(thumbnailError?.response?.data?.detail || 'Failed to regenerate thumbnails.');
    } finally {
      setRefreshingThumbnails(false);
    }
  };

  const handleReset = () => {
    if (videoUrl) {
      URL.revokeObjectURL(videoUrl);
    }

    resetThumbnailObjects();

    setStep('input');
    setError('');
    setScript(null);
    setVideoId('');
    setVideoData(null);
    setVideoUrl('');
    setChannelPreviews({});
    setSelectedAccountIds([]);
    setPublishAt('');
    setPrivacyStatus('channel_default');
    setProgress({ completed: 0, total: 0 });
  };

  const renderSignedOut = () => (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center px-6">
      <div className="max-w-3xl space-y-8">
        <div className="space-y-4">
          <span className="inline-flex items-center rounded-full border border-purple-500/30 bg-purple-500/10 px-4 py-2 text-sm text-purple-200">
            Sign in to generate, connect channels, and publish Shorts
          </span>
          <h2 className="text-4xl md:text-6xl font-extrabold text-white leading-tight">
            Generate YouTube Shorts and publish them to multiple channels.
          </h2>
          <p className="text-lg text-slate-400 max-w-2xl mx-auto">
            Sign in first, then connect your YouTube accounts, render your Short, and upload it with AI-generated metadata in one flow.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <SignUpButton>
            <button className="rounded-xl bg-purple-600 px-6 py-3 font-semibold text-white transition hover:bg-purple-500">
              Create account
            </button>
          </SignUpButton>

          <SignInButton>
            <button className="rounded-xl border border-slate-600 px-6 py-3 font-semibold text-slate-100 transition hover:border-slate-400 hover:bg-slate-800">
              Sign in
            </button>
          </SignInButton>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen text-slate-50 font-sans p-6 overflow-x-hidden" style={{backgroundColor: '#0f172a'}}>
      <div className="max-w-7xl mx-auto space-y-12">

        <header className="flex flex-col gap-6 pt-8 md:flex-row md:items-start md:justify-between">
          <div className="text-center md:text-left">
            <h1 className="text-4xl md:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-500 mb-4">
              AI Shorts Generator
            </h1>
            <p className="text-slate-400 text-lg max-w-2xl">
              Create a vertical Short, connect multiple YouTube accounts, and upload it automatically with AI-generated metadata.
            </p>
          </div>

          <div className="flex items-center justify-center gap-3 md:justify-end">
            <Show when="signed-out">
              <SignInButton>
                <button className="rounded-xl border border-slate-600 px-4 py-2 font-semibold text-slate-100 transition hover:border-slate-400 hover:bg-slate-800">
                  Sign in
                </button>
              </SignInButton>
              <SignUpButton>
                <button className="rounded-xl bg-purple-600 px-4 py-2 font-semibold text-white transition hover:bg-purple-500">
                  Sign up
                </button>
              </SignUpButton>
            </Show>

            <Show when="signed-in">
              <UserButton />
            </Show>
          </div>
        </header>

        {!!error && (
          <div className="max-w-4xl mx-auto rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-100">
            {error}
          </div>
        )}

        <Show when="signed-out">{renderSignedOut()}</Show>

        <Show when="signed-in">
          {syncingUser ? (
            <div className="max-w-2xl mx-auto rounded-xl border border-slate-700 bg-slate-800/80 p-6 text-center text-slate-300">
              Preparing your workspace...
            </div>
          ) : (
            <>
              {step === 'input' && (
                <InputPanel onSubmit={handleGenerateScript} disabled={loading} />
              )}

              {step === 'script_review' && (
                <ScriptPreview
                  script={script}
                  setScript={setScript}
                  onProceed={handleProceedToGeneration}
                />
              )}

              {step === 'generating' && (
                <ProgressTracker
                  step={progress.completed >= progress.total && progress.total > 0 ? 'video' : 'assets'}
                  progress={progress}
                />
              )}

              {step === 'done' && videoData && (
                <>
                  <ProgressTracker step="done" progress={progress} />
                  <VideoPlayer url={videoUrl} thumbnailUrl={thumbnailUrl} thumbnailVariants={thumbnailVariants} metadata={videoData.metadata} onReset={handleReset} />
                  <PublishPanel
                    accounts={youtubeAccounts}
                    channelPreviews={channelPreviews}
                    selectedAccountIds={selectedAccountIds}
                    uploads={videoData.uploads || []}
                    connecting={connectingAccount}
                    uploading={queueingUpload}
                    metadata={videoData.upload_metadata}
                    thumbnailVariants={thumbnailVariants}
                    publishAt={publishAt}
                    privacyStatus={privacyStatus}
                    savingSelection={savingSelection}
                    savingPresetId={savingPresetId}
                    refreshingMetadata={refreshingMetadata}
                    refreshingThumbnails={refreshingThumbnails}
                    onToggleAccount={handleToggleAccount}
                    onConnect={handleConnectYoutube}
                    onDisconnect={handleDisconnectYoutube}
                    onPublishAtChange={setPublishAt}
                    onPrivacyStatusChange={setPrivacyStatus}
                    onSaveChannelPreset={handleSaveChannelPreset}
                    onSelectTitle={handleSelectTitle}
                    onSelectThumbnail={handleSelectThumbnail}
                    onUseSuggestedSchedule={handleUseSuggestedSchedule}
                    onRegenerateMetadata={handleRegenerateMetadata}
                    onRegenerateThumbnails={handleRegenerateThumbnails}
                    onUpload={handleUploadVideo}
                    onRetryUpload={handleRetryUpload}
                  />
                </>
              )}
            </>
          )}
        </Show>
      </div>
    </div>
  );
}

export default App;
