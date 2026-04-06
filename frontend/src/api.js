import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const AUTH_REQUIRED_ERROR = 'Authentication token is not ready.';

let authTokenGetter = null;
let pendingAuthTokenPromise = null;

const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use(async (config) => {
  if (!authTokenGetter) {
    return Promise.reject(new Error(AUTH_REQUIRED_ERROR));
  }

  if (!pendingAuthTokenPromise) {
    pendingAuthTokenPromise = (async () => {
      try {
        return await authTokenGetter();
      } catch {
        return null;
      } finally {
        pendingAuthTokenPromise = null;
      }
    })();
  }

  const token = await pendingAuthTokenPromise;

  if (!token) {
    return Promise.reject(new Error(AUTH_REQUIRED_ERROR));
  }

  config.headers = config.headers || {};
  config.headers.Authorization = `Bearer ${token}`;

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error),
);

export const configureApiAuth = (tokenGetter) => {
  authTokenGetter = tokenGetter;
  if (!tokenGetter) {
    pendingAuthTokenPromise = null;
  }
};

export const getApiOrigin = () => new URL(API_BASE).origin;

export const getCurrentUser = async () => {
  const { data } = await api.get('/me');
  return data;
};

export const generateScript = async (topic, style, duration) => {
  const { data } = await api.post('/generate-script', { topic, style, duration });
  return data;
};

export const renderVideo = async (videoId, script, voice) => {
  const { data } = await api.post(`/videos/${videoId}/render`, {
    script,
    voice,
  });
  return data;
};

export const getVideo = async (videoId) => {
  const { data } = await api.get(`/videos/${videoId}`);
  return data;
};

export const downloadVideo = async (videoId) => {
  const { data } = await api.get(`/videos/${videoId}/download`, {
    responseType: 'blob',
  });
  return URL.createObjectURL(data);
};

export const downloadThumbnail = async (videoId) => {
  const { data } = await api.get(`/videos/${videoId}/thumbnail`, {
    responseType: 'blob',
  });
  return URL.createObjectURL(data);
};

export const downloadThumbnailVariant = async (videoId, variantName) => {
  const { data } = await api.get(`/videos/${videoId}/thumbnail/${variantName}`, {
    responseType: 'blob',
  });
  return URL.createObjectURL(data);
};

export const updatePublishSelection = async (videoId, selection) => {
  const { data } = await api.patch(`/videos/${videoId}/publish-selection`, selection);
  return data;
};

export const regenerateUploadMetadata = async (videoId) => {
  const { data } = await api.post(`/videos/${videoId}/metadata/regenerate`);
  return data;
};

export const regenerateThumbnailVariants = async (videoId) => {
  const { data } = await api.post(`/videos/${videoId}/thumbnails/regenerate`);
  return data;
};

export const getYoutubeAccounts = async () => {
  const { data } = await api.get('/youtube/accounts');
  return data;
};

export const updateYoutubeAccountPreset = async (accountId, preset) => {
  const { data } = await api.patch(`/youtube/accounts/${accountId}/preset`, preset);
  return data;
};

export const getChannelPreview = async (videoId, accountId) => {
  const { data } = await api.get(`/videos/${videoId}/channel-preview/${accountId}`);
  return data;
};

export const startYoutubeConnect = async () => {
  const { data } = await api.post('/youtube/connect/start');
  return data;
};

export const disconnectYoutubeAccount = async (accountId) => {
  const { data } = await api.delete(`/youtube/accounts/${accountId}`);
  return data;
};

export const uploadVideoToYoutube = async (
  videoId,
  youtubeAccountIds,
  privacyStatus = 'private',
  publishAt = null,
) => {
  const { data } = await api.post(`/videos/${videoId}/upload`, {
    youtube_account_ids: youtubeAccountIds,
    privacy_status: privacyStatus,
    publish_at: publishAt,
  });
  return data;
};

export const retryUpload = async (uploadId) => {
  const { data } = await api.post(`/uploads/${uploadId}/retry`);
  return data;
};
