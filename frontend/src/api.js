import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

let authTokenGetter = null;

const api = axios.create({
  baseURL: API_BASE,
});

api.interceptors.request.use(async (config) => {
  if (authTokenGetter) {
    const token = await authTokenGetter();
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  }

  return config;
});

export const configureApiAuth = (tokenGetter) => {
  authTokenGetter = tokenGetter;
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

export const getYoutubeAccounts = async () => {
  const { data } = await api.get('/youtube/accounts');
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
