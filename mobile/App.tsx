import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEventListener } from 'expo';
import { useVideoPlayer, VideoView } from 'expo-video';

const API_BASE_URL = '';
const SEARCH_PAGE_LIMIT = 5;

const USER_PROFILES = [
  { id: 'default', title: 'Основной' },
  { id: 'second', title: 'Второй' },
] as const;

type UserId = typeof USER_PROFILES[number]['id'];


type ReadinessResponse = {
  ready: boolean;
  checks: {
    backend: boolean;
    jellyfin: boolean;
    transmission: boolean;
    active_adapter: string;
  };
  errors: Record<string, string>;
};

type MediaCandidate = {
  id: string;
  title: string;
  year: number | null;
  source: string;
  license_mode: string;
  description: string | null;
};

type SearchResponse = {
  query: string;
  count: number;
  limit: number;
  offset: number;
  has_more: boolean;
  items: MediaCandidate[];
  errors?: Record<string, string>;
};

type RequestDetail = {
  request: {
    id: string;
    candidate_id: string;
    status: string;
    error_message: string | null;
  };
  job: {
    status?: string;
    progress: number;
    output_path: string | null;
    external_id?: string | null;
    download_speed_kbps?: number | null;
    eta_seconds?: number | null;
    peers_connected?: number | null;
  } | null;
  candidate: {
    title: string;
    source: string;
  } | null;
};

type RequestsResponse = {
  items: RequestDetail[];
};

type PreparedMedia = {
  id: string;
  title: string;
  source: string;
  year: number | null;
  file_name: string | null;
  relative_path: string;
  stream_path: string;
  stream_url?: string | null;
};

type PreparedMediaResponse = {
  count: number;
  items: PreparedMedia[];
};


type AuthUser = {
  id: string;
  username: string;
};

type AuthTokenResponse = {
  token: string;
  token_type: string;
  user: AuthUser;
};

type WatchPositionItem = {
  media_id: string;
  position_seconds: number;
};

type WatchPositionsResponse = {
  count: number;
  items: WatchPositionItem[];
};

export default function App() {
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchMoreLoading, setSearchMoreLoading] = useState(false);
  const [requestLoadingId, setRequestLoadingId] = useState<string | null>(null);
  const [cancelLoadingId, setCancelLoadingId] = useState<string | null>(null);
  const [deleteMediaLoadingId, setDeleteMediaLoadingId] = useState<string | null>(null);

  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [requests, setRequests] = useState<RequestDetail[]>([]);
  const [preparedMedia, setPreparedMedia] = useState<PreparedMedia[]>([]);
  const [watchPositions, setWatchPositions] = useState<Record<string, number>>({});

  const [query, setQuery] = useState('');
  const [searchResult, setSearchResult] = useState<SearchResponse | null>(null);
  const [selectedMedia, setSelectedMedia] = useState<PreparedMedia | null>(null);
  const [activeTab, setActiveTab] = useState<'home' | 'library'>('home');
  const [authRestored, setAuthRestored] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [authUsername, setAuthUsername] = useState('');
  const [authPassword, setAuthPassword] = useState('');
  const [authInviteCode, setAuthInviteCode] = useState('');
  const [authLoading, setAuthLoading] = useState(false);
  const [passwordFormVisible, setPasswordFormVisible] = useState(false);
  const [currentPasswordInput, setCurrentPasswordInput] = useState('');
  const [newPasswordInput, setNewPasswordInput] = useState('');
  const [passwordChangeLoading, setPasswordChangeLoading] = useState(false);
  const [passwordChangeMessage, setPasswordChangeMessage] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    async function restoreAuthState() {
      const savedToken = await AsyncStorage.getItem('auth-token');

      if (!savedToken) {
        setAuthRestored(true);
        return;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
          headers: {
            Authorization: `Bearer ${savedToken}`,
          },
        });

        if (!response.ok) {
          await AsyncStorage.removeItem('auth-token');
          setAuthToken(null);
          setAuthUser(null);
          return;
        }

        setAuthToken(savedToken);
        setAuthUser((await response.json()) as AuthUser);
      } finally {
        setAuthRestored(true);
      }
    }

    restoreAuthState().catch(() => {
      setAuthToken(null);
      setAuthUser(null);
      setAuthRestored(true);
    });
  }, []);

  const apiHeaders = useMemo<Record<string, string>>(() => {
    const headers: Record<string, string> = {};

    if (authToken) {
      headers.Authorization = `Bearer ${authToken}`;
    }

    return headers;
  }, [authToken]);

  const clearUserScopedState = useCallback(() => {
    setSelectedMedia(null);
    setSearchResult(null);
    setQuery('');
    setSearchError(null);
    setRequestError(null);
    setSearchMoreLoading(false);
    setWatchPositions({});
  }, []);

  const submitAuth = useCallback(async () => {
    const username = authUsername.trim();
    const password = authPassword;

    if (!username || !password) {
      setAuthError('Введите логин и пароль.');
      return;
    }

    if (password.length < 6) {
      setAuthError('Пароль должен быть не короче 6 символов.');
      return;
    }

    setAuthLoading(true);
    setAuthError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/${authMode}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          password,
          invite_code: authMode === 'register' ? authInviteCode.trim() : undefined,
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response, `Auth HTTP ${response.status}`));
      }

      const data = (await response.json()) as AuthTokenResponse;

      await AsyncStorage.setItem('auth-token', data.token);
      setAuthToken(data.token);
      setAuthUser(data.user);
      setAuthPassword('');
      setAuthInviteCode('');
      clearUserScopedState();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Ошибка авторизации');
    } finally {
      setAuthLoading(false);
    }
  }, [authInviteCode, authMode, authPassword, authUsername, clearUserScopedState]);

  const logout = useCallback(async () => {
    if (authToken) {
      await fetch(`${API_BASE_URL}/api/auth/logout`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      }).catch(() => undefined);
    }

    await AsyncStorage.removeItem('auth-token');

    setAuthToken(null);
    setAuthUser(null);
    setAuthPassword('');
    clearUserScopedState();
    setRequests([]);
    setPreparedMedia([]);
  }, [authToken, clearUserScopedState]);

  const logoutAll = useCallback(async () => {
    if (authToken) {
      await fetch(`${API_BASE_URL}/api/auth/logout-all`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      }).catch(() => undefined);
    }

    await AsyncStorage.removeItem('auth-token');

    setAuthToken(null);
    setAuthUser(null);
    setAuthPassword('');
    clearUserScopedState();
    setRequests([]);
    setPreparedMedia([]);
  }, [authToken, clearUserScopedState]);

  const changePassword = useCallback(async () => {
    if (!authToken) {
      return;
    }

    if (currentPasswordInput.length < 6 || newPasswordInput.length < 6) {
      setPasswordChangeMessage('Пароль должен быть не короче 6 символов.');
      return;
    }

    setPasswordChangeLoading(true);
    setPasswordChangeMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/change-password`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          current_password: currentPasswordInput,
          new_password: newPasswordInput,
        }),
      });

      if (!response.ok) {
        throw new Error(await readApiError(response, `Change password HTTP ${response.status}`));
      }

      await AsyncStorage.removeItem('auth-token');

      setAuthToken(null);
      setAuthUser(null);
      setAuthPassword('');
      setCurrentPasswordInput('');
      setNewPasswordInput('');
      setPasswordFormVisible(false);
      setPasswordChangeMessage(null);
      clearUserScopedState();
      setRequests([]);
      setPreparedMedia([]);
    } catch (err) {
      setPasswordChangeMessage(err instanceof Error ? err.message : 'Ошибка смены пароля');
    } finally {
      setPasswordChangeLoading(false);
    }
  }, [authToken, clearUserScopedState, currentPasswordInput, newPasswordInput]);

  const loadData = useCallback(async () => {
    if (!authToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const [readinessResponse, requestsResponse, preparedResponse, positionsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/readiness`),
        fetch(`${API_BASE_URL}/api/requests?limit=20`, { headers: apiHeaders }),
        fetch(`${API_BASE_URL}/api/media/prepared`, { headers: apiHeaders }),
        fetch(`${API_BASE_URL}/api/watch-positions`, { headers: apiHeaders }),
      ]);

      if (!readinessResponse.ok) {
        throw new Error(`Readiness HTTP ${readinessResponse.status}`);
      }

      if (!requestsResponse.ok) {
        throw new Error(`Requests HTTP ${requestsResponse.status}`);
      }

      if (!preparedResponse.ok) {
        throw new Error(`Prepared media HTTP ${preparedResponse.status}`);
      }

      if (!positionsResponse.ok) {
        throw new Error(`Watch positions HTTP ${positionsResponse.status}`);
      }

      const readinessJson = (await readinessResponse.json()) as ReadinessResponse;
      const requestsJson = (await requestsResponse.json()) as RequestsResponse;
      const preparedJson = (await preparedResponse.json()) as PreparedMediaResponse;
      const positionsJson = (await positionsResponse.json()) as WatchPositionsResponse;

      const nextWatchPositions: Record<string, number> = {};

      for (const item of positionsJson.items) {
        if (item.position_seconds > 0) {
          nextWatchPositions[item.media_id] = item.position_seconds;
        }
      }

      setReadiness(readinessJson);
      setRequests(requestsJson.items);
      setPreparedMedia(preparedJson.items);
      setWatchPositions(nextWatchPositions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Неизвестная ошибка');
    } finally {
      setLoading(false);
    }
  }, [apiHeaders, authToken]);

  const runSearch = useCallback(async () => {
    const normalizedQuery = query.trim();

    if (!normalizedQuery) {
      setSearchError('Введите название фильма.');
      return;
    }

    setSearchLoading(true);
    setSearchError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/search/all`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...apiHeaders,
        },
        body: JSON.stringify({
          query: normalizedQuery,
          year: extractYear(normalizedQuery),
          max_size_gb: 25,
          prefer_quality: '1080p',
          limit: SEARCH_PAGE_LIMIT,
          offset: 0,
        }),
      });

      if (!response.ok) {
        throw new Error(`Search HTTP ${response.status}`);
      }

      setSearchResult((await response.json()) as SearchResponse);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Ошибка поиска');
    } finally {
      setSearchLoading(false);
    }
  }, [apiHeaders, query]);

  const loadMoreSearch = useCallback(async () => {
    const normalizedQuery = query.trim();

    if (!normalizedQuery || !searchResult?.has_more || searchMoreLoading) {
      return;
    }

    setSearchMoreLoading(true);
    setSearchError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/search/all`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...apiHeaders,
        },
        body: JSON.stringify({
          query: normalizedQuery,
          year: extractYear(normalizedQuery),
          max_size_gb: 25,
          prefer_quality: '1080p',
          limit: SEARCH_PAGE_LIMIT,
          offset: searchResult.items.length,
        }),
      });

      if (!response.ok) {
        throw new Error(`Search HTTP ${response.status}`);
      }

      const nextPage = (await response.json()) as SearchResponse;

      setSearchResult((previous) => {
        if (!previous) {
          return nextPage;
        }

        const existingIds = new Set(previous.items.map((item) => item.id));
        const newItems = nextPage.items.filter((item) => !existingIds.has(item.id));

        return {
          ...nextPage,
          items: [...previous.items, ...newItems],
        };
      });
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Ошибка дозагрузки');
    } finally {
      setSearchMoreLoading(false);
    }
  }, [apiHeaders, query, searchMoreLoading, searchResult]);


  const saveWatchPosition = useCallback(async (mediaId: string, seconds: number) => {
    const normalizedSeconds = Math.max(0, Math.floor(seconds));

    setWatchPositions((previous) => ({
      ...previous,
      [mediaId]: normalizedSeconds,
    }));

    if (!authToken) {
      return;
    }

    try {
      await fetch(`${API_BASE_URL}/api/watch-positions/${encodeURIComponent(mediaId)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...apiHeaders,
        },
        body: JSON.stringify({
          position_seconds: normalizedSeconds,
        }),
      });
    } catch {
      // Сохранение позиции не должно ломать просмотр.
    }
  }, [apiHeaders, authToken]);


  const refreshActiveRequests = useCallback(async () => {
    try {
      await fetch(`${API_BASE_URL}/api/requests/refresh-active`, {
        method: 'POST',
        headers: apiHeaders,
      });
    } catch {
      // refresh-active не должен ломать основной экран
    }
  }, [apiHeaders]);


  const deletePreparedMedia = useCallback(async (candidateId: string) => {
    setDeleteMediaLoadingId(candidateId);
    setRequestError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/media/prepared/${candidateId}`, {
        method: 'DELETE',
        headers: apiHeaders,
      });

      if (!response.ok) {
        throw new Error(`Delete HTTP ${response.status}`);
      }

      if (selectedMedia?.id === candidateId) {
        setSelectedMedia(null);
      }

      setWatchPositions((previous) => {
        const next = { ...previous };
        delete next[candidateId];
        return next;
      });

      await fetch(`${API_BASE_URL}/api/watch-positions/${encodeURIComponent(candidateId)}`, {
        method: 'DELETE',
        headers: apiHeaders,
      }).catch(() => undefined);

      await loadData();
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Ошибка удаления фильма');
    } finally {
      setDeleteMediaLoadingId(null);
    }
  }, [apiHeaders, loadData, selectedMedia]);


  const cancelRequest = useCallback(async (requestId: string) => {
    setCancelLoadingId(requestId);
    setRequestError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/requests/${requestId}/cancel`, {
        method: 'POST',
        headers: apiHeaders,
      });

      if (!response.ok) {
        throw new Error(`Cancel HTTP ${response.status}`);
      }

      await loadData();
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Ошибка отмены загрузки');
    } finally {
      setCancelLoadingId(null);
    }
  }, [apiHeaders, loadData]);


  const createRequest = useCallback(async (candidateId: string) => {
    setRequestLoadingId(candidateId);
    setRequestError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/requests`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...apiHeaders,
        },
        body: JSON.stringify({
          candidate_id: candidateId,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request HTTP ${response.status}`);
      }

      const createdRequest = (await response.json()) as RequestDetail;

      setRequests((previous) => {
        const withoutDuplicate = previous.filter(
          (item) => item.request.id !== createdRequest.request.id,
        );

        return [createdRequest, ...withoutDuplicate];
      });

      await refreshActiveRequests();

      setTimeout(() => {
        refreshActiveRequests()
          .then(() => loadData())
          .catch(() => undefined);
      }, 2500);

      setTimeout(() => {
        refreshActiveRequests()
          .then(() => loadData())
          .catch(() => undefined);
      }, 7000);
    } catch (err) {
      setRequestError(err instanceof Error ? err.message : 'Ошибка создания заявки');
    } finally {
      setRequestLoadingId(null);
    }
  }, [apiHeaders, loadData, refreshActiveRequests]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const hasActiveRequests = useMemo(
    () => requests.some((item) => ['created', 'queued', 'running', 'downloading', 'importing', 'scanning'].includes(item.request.status)),
    [requests],
  );

  useEffect(() => {
    if (!hasActiveRequests) {
      return;
    }

    const intervalId = setInterval(() => {
      refreshActiveRequests()
        .then(() => loadData())
        .catch(() => undefined);
    }, 5000);

    return () => {
      clearInterval(intervalId);
    };
  }, [hasActiveRequests, loadData, refreshActiveRequests]);

  const selectedStreamUrl = selectedMedia
    ? selectedMedia.stream_url ?? `${API_BASE_URL}${selectedMedia.stream_path}`
    : null;

  const serviceProblem = formatServiceProblem(readiness, error);

  const inProgressMedia = preparedMedia.filter((item) => (watchPositions[item.id] ?? 0) > 0);
  const readyMedia = preparedMedia.filter((item) => (watchPositions[item.id] ?? 0) <= 0);
  const activeDownloadRequests = requests.filter((item) =>
    isActiveDownloadStatus(item.request.status),
  );

  const downloadRequestsForDisplay = useMemo(() => {
    const seen = new Set<string>();
    const result: RequestDetail[] = [];

    for (const item of requests) {
      if (!isActiveDownloadStatus(item.request.status) && !isTerminalDownloadStatus(item.request.status)) {
        continue;
      }

      if (seen.has(item.request.id)) {
        continue;
      }

      seen.add(item.request.id);
      result.push(item);
    }

    return result.slice(0, 12);
  }, [requests]);

  const preparedMediaIds = useMemo(
    () => new Set(preparedMedia.map((item) => item.id)),
    [preparedMedia],
  );

  const preparedMediaTitleKeys = useMemo(
    () => new Set(preparedMedia.map((item) => candidateTitleKey(item.title))),
    [preparedMedia],
  );

  const activeRequestByCandidateId = useMemo(() => {
    const map = new Map<string, RequestDetail>();

    for (const item of activeDownloadRequests) {
      map.set(item.request.candidate_id, item);
    }

    return map;
  }, [activeDownloadRequests]);

  const activeRequestByCandidateTitleKey = useMemo(() => {
    const map = new Map<string, RequestDetail>();

    for (const item of activeDownloadRequests) {
      const title = item.candidate?.title;

      if (title) {
        map.set(candidateTitleKey(title), item);
      }
    }

    return map;
  }, [activeDownloadRequests]);


  if (!authRestored) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" />
        <View style={styles.container}>
          <View style={styles.card}>
            <ActivityIndicator />
            <Text style={styles.mutedText}>Проверяем вход...</Text>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  if (!authToken || !authUser) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <StatusBar barStyle="light-content" />

        <ScrollView contentContainerStyle={styles.container}>
          <View style={styles.headerRow}>
            <View style={styles.titleBlock}>
              <Text style={styles.title}>Фильмы</Text>
              <Text style={styles.subtitle}>Войдите, чтобы продолжить просмотр с любого устройства</Text>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>
              {authMode === 'login' ? 'Вход' : 'Регистрация'}
            </Text>

            <TextInput
              value={authUsername}
              onChangeText={setAuthUsername}
              placeholder="Логин"
              placeholderTextColor="#6b7280"
              style={styles.input}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
            />

            <TextInput
              value={authPassword}
              onChangeText={setAuthPassword}
              placeholder="Пароль"
              placeholderTextColor="#6b7280"
              style={styles.input}
              secureTextEntry
              returnKeyType="done"
              onSubmitEditing={submitAuth}
            />

            {authMode === 'register' && (
              <TextInput
                value={authInviteCode}
                onChangeText={setAuthInviteCode}
                placeholder="Код приглашения, если нужен"
                placeholderTextColor="#6b7280"
                style={styles.input}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="done"
                onSubmitEditing={submitAuth}
              />
            )}

            {authError && (
              <Text style={styles.errorText}>{authError}</Text>
            )}

            <TouchableOpacity style={styles.primaryButton} onPress={submitAuth} disabled={authLoading}>
              <Text style={styles.buttonText}>
                {authLoading
                  ? 'Проверяем...'
                  : authMode === 'login'
                    ? 'Войти'
                    : 'Создать аккаунт'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.secondaryButton}
              onPress={() => {
                setAuthMode(authMode === 'login' ? 'register' : 'login');
                setAuthError(null);
              }}
            >
              <Text style={styles.secondaryButtonText}>
                {authMode === 'login'
                  ? 'Создать новый аккаунт'
                  : 'Уже есть аккаунт — войти'}
              </Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" />

      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.headerRow}>
          <View style={styles.titleBlock}>
            <Text style={styles.title}>Фильмы</Text>
            <Text style={styles.subtitle}>Поиск, подготовка и просмотр</Text>
          </View>

          <Text
            style={[
              styles.statusPill,
              loading ? styles.pillNeutral : readiness?.ready ? styles.pillOk : styles.pillBad,
            ]}
          >
            {loading ? '…' : readiness?.ready ? '✓' : '✕'}
          </Text>
        </View>

        {serviceProblem && (
          <Text style={styles.topErrorText}>{serviceProblem}</Text>
        )}

        <View style={styles.profileAuthRow}>
          <Text style={styles.profileAuthText}>
            Аккаунт: {authUser?.username ?? 'неизвестно'}
          </Text>

          <TouchableOpacity style={styles.profileLogoutButton} onPress={logout}>
            <Text style={styles.profileLogoutText}>Выйти</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.profileAuthRow}>
          <TouchableOpacity
            style={styles.profileLogoutButton}
            onPress={() => {
              setPasswordFormVisible((value) => !value);
              setPasswordChangeMessage(null);
            }}
          >
            <Text style={styles.profileLogoutText}>Сменить пароль</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.profileLogoutButton} onPress={logoutAll}>
            <Text style={styles.profileLogoutText}>Выйти везде</Text>
          </TouchableOpacity>
        </View>

        {passwordFormVisible && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Сменить пароль</Text>

            <TextInput
              value={currentPasswordInput}
              onChangeText={setCurrentPasswordInput}
              placeholder="Текущий пароль"
              placeholderTextColor="#6b7280"
              style={styles.input}
              secureTextEntry
              returnKeyType="next"
            />

            <TextInput
              value={newPasswordInput}
              onChangeText={setNewPasswordInput}
              placeholder="Новый пароль"
              placeholderTextColor="#6b7280"
              style={styles.input}
              secureTextEntry
              returnKeyType="done"
              onSubmitEditing={changePassword}
            />

            {passwordChangeMessage && (
              <Text style={styles.errorText}>{passwordChangeMessage}</Text>
            )}

            <TouchableOpacity
              style={styles.primaryButton}
              onPress={changePassword}
              disabled={passwordChangeLoading}
            >
              <Text style={styles.buttonText}>
                {passwordChangeLoading ? 'Сохраняем...' : 'Сохранить пароль'}
              </Text>
            </TouchableOpacity>

            <Text style={styles.mutedText}>
              После смены пароля нужно будет войти заново на всех устройствах.
            </Text>
          </View>
        )}

        {selectedMedia && selectedStreamUrl && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{selectedMedia.title}</Text>
            <MoviePlayer
              key={selectedStreamUrl}
              uri={selectedStreamUrl}
              mediaId={selectedMedia.id}
              initialPosition={watchPositions[selectedMedia.id] ?? 0}
              onPositionSaved={(seconds) => {
                saveWatchPosition(selectedMedia.id, seconds);
              }}
            />

            <TouchableOpacity style={styles.secondaryButton} onPress={() => setSelectedMedia(null)}>
              <Text style={styles.secondaryButtonText}>Закрыть плеер</Text>
            </TouchableOpacity>
          </View>
        )}

        {activeTab === 'home' && (
          <>
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Найти фильм</Text>

          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Введите название"
            placeholderTextColor="#6b7280"
            style={styles.input}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            onSubmitEditing={runSearch}
          />

          {searchError && (
            <Text style={styles.errorText}>{searchError}</Text>
          )}

          {requestError && (
            <Text style={styles.errorText}>{requestError}</Text>
          )}

          <TouchableOpacity style={styles.primaryButton} onPress={runSearch} disabled={searchLoading}>
            <Text style={styles.buttonText}>
              {searchLoading ? 'Ищем...' : 'Найти'}
            </Text>
          </TouchableOpacity>

          {searchResult && (
            <View style={styles.listBlock}>
              <Text style={styles.mutedText}>Показано: {searchResult.items.length} из {searchResult.count}</Text>

              {searchResult.items.map((item) => (
                <View key={item.id} style={styles.mediaItem}>
                  <Text style={styles.itemTitle}>{item.title}</Text>
                  <Text style={styles.itemMeta}>
                    {formatCandidateMeta(item)}
                  </Text>

                  {(() => {
                    const titleKey = candidateTitleKey(item.title);
                    const relatedRequest = requests.find((requestItem) => {
                      const requestTitle = requestItem.candidate?.title ?? '';

                      return (
                        requestItem.request.candidate_id === item.id ||
                        Boolean(requestTitle && candidateTitleKey(requestTitle) === titleKey)
                      );
                    });
                    const activeRequest =
                      activeRequestByCandidateId.get(item.id) ??
                      activeRequestByCandidateTitleKey.get(titleKey);
                    const isPrepared = preparedMediaIds.has(item.id) || preparedMediaTitleKeys.has(titleKey);
                    const isCompletedWithoutMedia = relatedRequest?.request.status === 'completed' && !isPrepared;
                    const isRetryable =
                      relatedRequest !== undefined &&
                      ['failed', 'cancelled'].includes(relatedRequest.request.status);
                    const isBusy = requestLoadingId === item.id || Boolean(activeRequest) || isPrepared;

                    let buttonText = 'Подготовить';

                    if (requestLoadingId === item.id) {
                      buttonText = 'Готовим...';
                    } else if (isPrepared) {
                      buttonText = 'В медиатеке';
                    } else if (activeRequest) {
                      buttonText = translateStatus(activeRequest.request.status);
                    } else if (isCompletedWithoutMedia) {
                      buttonText = 'Подготовить заново';
                    } else if (isRetryable) {
                      buttonText = 'Повторить подготовку';
                    }

                    return (
                      <TouchableOpacity
                        style={[styles.secondaryButton, isBusy && styles.disabledButton]}
                        onPress={() => createRequest(item.id)}
                        disabled={isBusy}
                      >
                        <Text style={styles.secondaryButtonText}>{buttonText}</Text>
                      </TouchableOpacity>
                    );
                  })()}
                </View>
              ))}

              {searchResult.has_more && (
                <TouchableOpacity
                  style={styles.secondaryButton}
                  onPress={loadMoreSearch}
                  disabled={searchMoreLoading || searchLoading}
                >
                  <Text style={styles.secondaryButtonText}>
                    {searchMoreLoading ? 'Загружаем...' : 'Показать больше'}
                  </Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Продолжить просмотр</Text>

          {inProgressMedia.length === 0 ? (
            <Text style={styles.mutedText}>Незаконченных фильмов пока нет.</Text>
          ) : (
            inProgressMedia.map((item) => (
              <View key={item.id} style={styles.mediaItem}>
                <Text style={styles.itemTitle}>{item.title}</Text>
                <Text style={styles.itemMeta}>
                  {item.source} · остановлено на {formatTime(watchPositions[item.id] ?? 0)}
                </Text>

                <TouchableOpacity style={styles.primaryButton} onPress={() => setSelectedMedia(item)}>
                  <Text style={styles.buttonText}>Продолжить</Text>
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>

          </>
        )}

        {activeTab === 'library' && (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Медиатека</Text>

            <View style={styles.listBlock}>
              <Text style={styles.itemTitle}>Загрузки и подготовка</Text>

              {downloadRequestsForDisplay.length === 0 ? (
                <Text style={styles.mutedText}>Активных загрузок пока нет.</Text>
              ) : (
                downloadRequestsForDisplay.map((item) => {
                  const errorMessage = item.request.error_message;
                  const candidateTitle = item.candidate?.title ?? item.request.candidate_id;
                  const isActive = isActiveDownloadStatus(item.request.status);

                  return (
                    <View key={item.request.id} style={styles.mediaItem}>
                      <Text style={styles.itemTitle}>{candidateTitle}</Text>
                      <Text style={styles.itemMeta}>
                        {formatDownloadStatusLine(item)}
                        {isActive ? ' · выполняется сейчас' : ''}
                      </Text>

                      {errorMessage && (
                        <Text style={styles.errorText}>{errorMessage}</Text>
                      )}
                    </View>
                  );
                })
              )}

              <TouchableOpacity
                style={styles.secondaryButton}
                onPress={async () => {
                  await refreshActiveRequests();
                  await loadData();
                }}
              >
                <Text style={styles.secondaryButtonText}>Обновить статусы</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.librarySection}>
              <View style={styles.rowBetween}>
                <Text style={styles.sectionTitle}>Загружается</Text>
                {activeDownloadRequests.length > 0 && (
                  <Text style={[styles.statusPill, styles.pillNeutral]}>
                    {activeDownloadRequests.length}
                  </Text>
                )}
              </View>

              {activeDownloadRequests.length === 0 ? (
                <Text style={styles.mutedText}>Активных загрузок нет.</Text>
              ) : (
                activeDownloadRequests.map((item) => (
                  <View key={item.request.id} style={styles.mediaItem}>
                    <View style={styles.downloadHeader}>
                      <Text style={styles.downloadTitle} numberOfLines={2}>
                        {item.candidate?.title ?? item.request.candidate_id}
                      </Text>

                      <Text style={[styles.statusPill, statusStyle(item.request.status)]}>
                        {translateStatus(item.request.status)}
                      </Text>
                    </View>

                    <Text style={styles.itemMeta}>
                      {item.candidate?.source ?? 'источник неизвестен'} · {item.job?.progress ?? 0}%
                    </Text>

                    {item.request.error_message && (
                      <Text style={styles.errorText}>{item.request.error_message}</Text>
                    )}

                    <TouchableOpacity
                      style={styles.dangerButton}
                      onPress={() => cancelRequest(item.request.id)}
                      disabled={cancelLoadingId === item.request.id}
                    >
                      <Text style={styles.dangerButtonText}>
                        {cancelLoadingId === item.request.id ? 'Останавливаем...' : 'Остановить и удалить'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                ))
              )}
            </View>

            <View style={styles.librarySection}>
              <Text style={styles.sectionTitle}>Готово к просмотру</Text>

              {preparedMedia.length === 0 ? (
                <Text style={styles.mutedText}>Подготовленных фильмов пока нет.</Text>
              ) : (
                preparedMedia.map((item) => {
                  const savedPosition = watchPositions[item.id] ?? 0;

                  return (
                    <View key={item.id} style={styles.mediaItem}>
                      <Text style={styles.itemTitle}>{item.title}</Text>
                      <Text style={styles.itemMeta}>
                        {item.source} · {item.year ?? 'год неизвестен'}
                        {savedPosition > 0 ? ` · остановлено на ${formatTime(savedPosition)}` : ''}
                      </Text>

                      <TouchableOpacity style={styles.primaryButton} onPress={() => setSelectedMedia(item)}>
                        <Text style={styles.buttonText}>
                          {savedPosition > 0 ? 'Продолжить' : 'Смотреть'}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.dangerButton}
                        onPress={() => deletePreparedMedia(item.id)}
                        disabled={deleteMediaLoadingId === item.id}
                      >
                        <Text style={styles.dangerButtonText}>
                          {deleteMediaLoadingId === item.id ? 'Удаляем...' : 'Удалить'}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  );
                })
              )}
            </View>
          </View>
        )}
      </ScrollView>

      <View style={styles.bottomNav}>
        <TouchableOpacity
          style={[styles.tabButton, activeTab === 'home' && styles.tabButtonActive]}
          onPress={() => setActiveTab('home')}
        >
          <Text style={[styles.tabText, activeTab === 'home' && styles.tabTextActive]}>
            Главная
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.tabButton, activeTab === 'library' && styles.tabButtonActive]}
          onPress={() => setActiveTab('library')}
        >
          <Text style={[styles.tabText, activeTab === 'library' && styles.tabTextActive]}>
            Медиатека
          </Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

function profileTitle(userId: UserId): string {
  return USER_PROFILES.find((profile) => profile.id === userId)?.title ?? userId;
}


function candidateTitleKey(value: string | null | undefined): string {
  return (value ?? '').trim().toLowerCase().replace(/\s+/g, ' ');
}


function normalizeUserId(value: string | null): UserId {
  const foundProfile = USER_PROFILES.find((profile) => profile.id === value);

  return foundProfile?.id ?? 'default';
}


function formatServiceProblem(
  readiness: ReadinessResponse | null,
  error: string | null,
): string | null {
  if (error) {
    return error;
  }

  if (!readiness || readiness.ready) {
    return null;
  }

  const firstError = Object.values(readiness.errors ?? {})[0];

  return firstError ?? 'Backend недоступен.';
}



const DOWNLOAD_ACTIVE_STATUSES = new Set([
  'created',
  'queued',
  'running',
  'downloading',
  'importing',
  'scanning',
]);

const DOWNLOAD_TERMINAL_STATUSES = new Set([
  'completed',
  'failed',
  'cancelled',
  'deleted',
]);

function isActiveDownloadStatus(status: string): boolean {
  return DOWNLOAD_ACTIVE_STATUSES.has(status);
}

function isTerminalDownloadStatus(status: string): boolean {
  return DOWNLOAD_TERMINAL_STATUSES.has(status);
}

function formatDownloadProgress(item: RequestDetail): string {
  const progress = item.job?.progress;

  if (typeof progress !== 'number' || !Number.isFinite(progress)) {
    return '';
  }

  return ` · ${Math.max(0, Math.min(100, Math.round(progress)))}%`;
}

function formatDownloadStatusLine(item: RequestDetail): string {
  const status = translateStatus(item.request.status);
  const progress = formatDownloadProgress(item);
  const speed = formatDownloadSpeed(item.job?.download_speed_kbps);
  const eta = formatShortDuration(item.job?.eta_seconds);
  const peers = item.job?.peers_connected;

  const speedText = speed ? ` · ${speed}` : '';
  const etaText = eta ? ` · осталось ${eta}` : '';
  const peersText = typeof peers === 'number' ? ` · пиров ${peers}` : '';
  const externalId = item.job?.external_id ? ` · torrent #${item.job.external_id}` : '';

  return `${status}${progress}${speedText}${etaText}${peersText}${externalId}`;
}

function formatShortDuration(totalSeconds?: number | null): string {
  if (!totalSeconds || totalSeconds <= 0 || !Number.isFinite(totalSeconds)) {
    return '';
  }

  const seconds = Math.max(60, Math.round(totalSeconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.max(1, Math.round((seconds % 3600) / 60));

  if (days > 0) {
    return `${days} д ${hours} ч`;
  }

  if (hours > 0) {
    return `${hours} ч ${minutes} мин`;
  }

  return `${minutes} мин`;
}

function formatApproxDownloadTime(totalSeconds?: number | null): string | null {
  const label = formatShortDuration(totalSeconds);

  if (!label) {
    return null;
  }

  return `примерно ${label}`;
}

function formatDownloadSpeed(kbps?: number | null): string | null {
  if (!kbps || kbps <= 0 || !Number.isFinite(kbps)) {
    return null;
  }

  if (kbps >= 1024) {
    return `${(kbps / 1024).toFixed(1)} МБ/с`;
  }

  return `${Math.round(kbps)} КБ/с`;
}

function formatDurationLabel(totalSeconds?: number | null): string {
  if (!totalSeconds || totalSeconds <= 0 || !Number.isFinite(totalSeconds)) {
    return 'неизвестна';
  }

  const seconds = Math.floor(totalSeconds);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);

  if (hours <= 0) {
    return `${minutes} мин`;
  }

  if (minutes <= 0) {
    return `${hours} ч`;
  }

  return `${hours} ч ${minutes} мин`;
}

function formatCandidateMeta(item: {
  source: string;
  year?: number | null;
  quality_label?: string | null;
  audio_label?: string | null;
  size_gb?: number | null;
  duration_seconds?: number | null;
  seeders?: number | null;
  peers?: number | null;
  estimated_download_seconds?: number | null;
}): string {
  const parts = [
    item.quality_label,
    item.audio_label,
    item.size_gb ? `${item.size_gb} ГБ` : null,
    formatApproxDownloadTime(item.estimated_download_seconds),
    item.duration_seconds
      ? `длительность ${formatDurationLabel(item.duration_seconds)}`
      : 'длительность неизвестна',
    item.year ? String(item.year) : null,
  ].filter(Boolean);

  if (parts.length > 0) {
    return parts.join(' · ');
  }

  return `${item.source} · ${item.year ?? 'год неизвестен'}`;
}


function extractYear(value: string): number | null {
  const match = value.match(/\b(18|19|20)\d{2}\b/);

  if (!match) {
    return null;
  }

  return Number(match[0]);
}


function MoviePlayer({
  uri,
  mediaId,
  initialPosition,
  onPositionSaved,
}: {
  uri: string;
  mediaId: string;
  initialPosition: number;
  onPositionSaved: (seconds: number) => void;
}) {
  const initialPositionRef = useRef(Math.max(0, Math.floor(initialPosition)));
  const lastSavedSecondRef = useRef(0);
  const currentSecondRef = useRef(0);
  const onPositionSavedRef = useRef(onPositionSaved);

  useEffect(() => {
    onPositionSavedRef.current = onPositionSaved;
  }, [onPositionSaved]);

  const player = useVideoPlayer(uri, (playerInstance) => {
    playerInstance.timeUpdateEventInterval = 2;
  });

  useEffect(() => {
    let cancelled = false;

    async function restorePosition() {
      const savedSeconds = initialPositionRef.current;

      if (cancelled) {
        return;
      }

      if (Number.isFinite(savedSeconds) && savedSeconds > 5) {
        player.currentTime = savedSeconds;
        currentSecondRef.current = savedSeconds;
        lastSavedSecondRef.current = savedSeconds;
      }

      player.play();
    }

    restorePosition().catch(() => {
      player.play();
    });

    return () => {
      cancelled = true;

      const rewindedSecond = Math.max(0, currentSecondRef.current - 10);

      if (rewindedSecond > 0) {
        onPositionSavedRef.current(rewindedSecond);
      }
    };
  }, [mediaId, player]);

  useEventListener(player, 'timeUpdate', (payload) => {
    const currentTime = Math.floor(payload.currentTime ?? 0);

    if (currentTime <= 0) {
      return;
    }

    currentSecondRef.current = currentTime;

    if (Math.abs(currentTime - lastSavedSecondRef.current) < 5) {
      return;
    }

    lastSavedSecondRef.current = currentTime;
    onPositionSaved(currentTime);
  });

  return (
    <View>
      <VideoView
        style={styles.video}
        player={player}
        nativeControls
        fullscreenOptions={{ enable: true }}
        contentFit="contain"
      />
    </View>
  );
}

function formatTime(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);

  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

async function readApiError(response: Response, fallback: string): Promise<string> {
  try {
    const data = await response.json();

    if (typeof data?.detail === 'string') {
      return data.detail;
    }

    if (Array.isArray(data?.detail) && data.detail[0]?.msg) {
      return String(data.detail[0].msg);
    }
  } catch {
    // ignore malformed error body
  }

  return fallback;
}


function translateStatus(status: string): string {
  const labels: Record<string, string> = {
    created: 'создано',
    queued: 'в очереди',
    running: 'запуск',
    downloading: 'загрузка',
    importing: 'импорт',
    scanning: 'сканирование',
    completed: 'готово',
    failed: 'ошибка',
    cancelled: 'отменено',
  };

  return labels[status] ?? status;
}


function statusStyle(status: string) {
  if (status === 'completed') {
    return styles.pillOk;
  }

  if (status === 'failed') {
    return styles.pillBad;
  }

  if (status === 'cancelled') {
    return styles.pillNeutral;
  }

  return styles.pillNeutral;
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#111827',
  },
  container: {
    flexGrow: 1,
    padding: 20,
    paddingTop: 72,
    paddingBottom: 108,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 18,
  },
  titleBlock: {
    flex: 1,
  },
  topErrorText: {
    color: '#fecaca',
    fontSize: 12,
    lineHeight: 18,
    marginTop: -10,
    marginBottom: 14,
  },

  profileAuthRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 12,
  },
  profileAuthText: {
    color: '#9ca3af',
    fontSize: 13,
    fontWeight: '700',
  },
  profileLogoutButton: {
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: 999,
    backgroundColor: '#374151',
  },
  profileLogoutText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '800',
  },
  pinCard: {
    backgroundColor: '#111827',
    borderColor: '#374151',
    borderWidth: 1,
    borderRadius: 18,
    padding: 14,
    marginBottom: 16,
  },

  profileRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  profileButton: {
    flex: 1,
    backgroundColor: '#1f2937',
    borderRadius: 999,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#374151',
  },
  profileButtonActive: {
    backgroundColor: '#2563eb',
    borderColor: '#60a5fa',
  },
  profileButtonText: {
    color: '#9ca3af',
    fontSize: 14,
    fontWeight: '800',
  },
  profileButtonTextActive: {
    color: '#ffffff',
  },

  title: {
    color: '#ffffff',
    fontSize: 34,
    fontWeight: '800',
    marginBottom: 4,
  },
  subtitle: {
    color: '#9ca3af',
    fontSize: 16,
    marginBottom: 24,
  },
  bottomNav: {
    position: 'absolute',
    left: 16,
    right: 16,
    bottom: 16,
    backgroundColor: '#1f2937',
    borderRadius: 22,
    padding: 6,
    flexDirection: 'row',
    gap: 6,
  },
  tabButton: {
    flex: 1,
    borderRadius: 16,
    paddingVertical: 12,
    alignItems: 'center',
  },
  tabButtonActive: {
    backgroundColor: '#2563eb',
  },
  tabText: {
    color: '#9ca3af',
    fontSize: 14,
    fontWeight: '800',
  },
  tabTextActive: {
    color: '#ffffff',
  },

  card: {
    backgroundColor: '#1f2937',
    borderRadius: 22,
    padding: 18,
    marginBottom: 16,
  },
  cardTitle: {
    color: '#ffffff',
    fontSize: 20,
    fontWeight: '800',
    marginBottom: 14,
  },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  mutedText: {
    color: '#9ca3af',
    fontSize: 14,
  },
  input: {
    backgroundColor: '#111827',
    borderColor: '#374151',
    borderWidth: 1,
    borderRadius: 16,
    color: '#ffffff',
    fontSize: 16,
    paddingHorizontal: 14,
    paddingVertical: 13,
    marginBottom: 12,
  },
  primaryButton: {
    marginTop: 12,
    backgroundColor: '#2563eb',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  smallButton: {
    marginTop: 14,
    backgroundColor: '#374151',
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: 'center',
  },
  disabledButton: {
    opacity: 0.55,
  },

  secondaryButton: {
    marginTop: 10,
    backgroundColor: '#374151',
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: 'center',
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '800',
  },
  secondaryButtonText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: '800',
  },
  statusPill: {
    overflow: 'hidden',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
    fontSize: 12,
    fontWeight: '800',
  },
  pillOk: {
    color: '#064e3b',
    backgroundColor: '#34d399',
  },
  pillBad: {
    color: '#7f1d1d',
    backgroundColor: '#fca5a5',
  },
  pillNeutral: {
    color: '#1e3a8a',
    backgroundColor: '#93c5fd',
  },
  errorText: {
    color: '#fca5a5',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
  },
  librarySection: {
    marginBottom: 18,
  },
  sectionTitle: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '800',
    marginBottom: 10,
  },

  listBlock: {
    marginTop: 16,
  },
  downloadHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  downloadTitle: {
    flex: 1,
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '800',
    lineHeight: 23,
  },
  dangerButton: {
    marginTop: 10,
    backgroundColor: '#7f1d1d',
    borderRadius: 14,
    paddingVertical: 12,
    alignItems: 'center',
  },
  dangerButtonText: {
    color: '#fecaca',
    fontSize: 14,
    fontWeight: '800',
  },

  mediaItem: {
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  itemTitle: {
    color: '#ffffff',
    fontSize: 17,
    fontWeight: '800',
  },
  itemMeta: {
    color: '#93c5fd',
    fontSize: 13,
    marginTop: 5,
  },
  itemDescription: {
    color: '#9ca3af',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 8,
  },
  requestItem: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#374151',
  },
  requestTitle: {
    color: '#ffffff',
    fontSize: 15,
    fontWeight: '800',
    flex: 1,
  },
  video: {
    width: '100%',
    height: 220,
    borderRadius: 16,
    backgroundColor: '#000000',
  },
  footer: {
    color: '#6b7280',
    fontSize: 12,
    marginTop: 2,
    marginBottom: 24,
    textAlign: 'center',
  },
});
