import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { type GeoJSONSource, type StyleSpecification } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import type { FeatureCollection, Geometry } from 'geojson';
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  Check,
  ChevronRight,
  Crosshair,
  History,
  Layers,
  Map as MapIcon,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Search,
  Send,
  Settings,
  Shield,
  Ship,
  Target,
  X,
} from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Entity } from '../generated/contracts';
maplibregl.setWorkerUrl(workerUrl);

type EntityView = Required<Omit<Entity, 'velocity'>> & {
  velocity: { eastMps: number; northMps: number };
  speedMps: number;
  bearingDegrees: number | null;
  displayVector: {
    horizonSeconds: number;
    endPosition: { longitude: number; latitude: number };
  } | null;
};
type Situation = {
  scenarioId?: string;
  epochId?: string;
  scenario?: {
    scenarioId: string;
    version: number;
    name: string;
    initialBounds: [number, number, number, number];
    zones: { id: string; name: string; domain: string; bounds: [number, number, number, number] }[];
  };
  entities: EntityView[];
  snapshotId?: string;
  sequence?: number;
  revision?: number;
  sourceTime?: string;
  simulationTime?: number;
  running?: boolean;
  platformCursor?: number;
  historyGap?: boolean;
};
type Course = {
  id: string;
  title: string;
  summary: string;
  evidenceIds: string[];
  expectedEffects: string[];
  risksAndConstraints: string[];
};
type Evidence = {
  evidenceId: string;
  tool: string;
  arguments: unknown;
  data: Record<string, unknown>;
};
type Run = {
  runId: string;
  conversationId: string | null;
  question: string;
  trigger: string;
  createdAt: string;
  updatedAt: string;
  status: string;
  selectedCourseId: string | null;
  sourceEvent?: { type: string };
  sourceContext?: { snapshotId?: string; sourceTime?: string };
  result: {
    answer: string;
    findings: { text: string; category: string; evidenceIds: string[] }[];
    evidenceIds: string[];
    limitations: string[];
    courses: Course[] | null;
  } | null;
  toolCalls: {
    name: string;
    callId: string;
    status: string;
    arguments: unknown;
    response: unknown;
    startedAt: string;
    endedAt?: string;
  }[];
  evidence: Evidence[];
  error?: string;
};
const labels: Record<string, string> = {
  friendly: '아군',
  hostile: '적군',
  unknown: '미확인',
  tank: '탱크',
  naval_vessel: '함정',
  armored_vehicle: '장갑차',
  support_vehicle: '지원 차량',
  uav: '무인기',
  serviceable: '정비 정상',
  maintenance: '정비 중',
  available: '가용',
  unavailable: '가용 불가',
  active: '활성',
  inactive: '비활성',
  queued: '대기',
  running: '분석 중',
  completed: '완료',
  failed: '실패',
  partial: '부분 결과',
  clarification: '추가 정보 필요',
  interrupted: '중단됨',
  timeout: '시간 초과',
  budget_exceeded: '실행 한도 도달',
  validation_failed: '결과 검증 실패',
  refused: '응답 제한',
};
const time = (value?: string) =>
  value
    ? new Date(value).toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })
    : '—';
const busy = (run: Run | null) => !!run && ['queued', 'running'].includes(run.status);

function icon(side: string, kind: string): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = 48;
  canvas.height = 48;
  const c = canvas.getContext('2d')!;
  c.lineWidth = 2.5;
  c.strokeStyle = side === 'friendly' ? '#79b8f0' : side === 'hostile' ? '#f08d8d' : '#b4bec7';
  c.fillStyle = '#121c25';
  if (kind === 'arrow') {
    c.fillStyle = c.strokeStyle;
    c.beginPath();
    c.moveTo(24, 9);
    c.lineTo(35, 34);
    c.lineTo(24, 28);
    c.lineTo(13, 34);
    c.closePath();
    c.fill();
    return c.getImageData(0, 0, 48, 48);
  }
  c.beginPath();
  if (side === 'hostile') {
    c.moveTo(24, 4);
    c.lineTo(44, 24);
    c.lineTo(24, 44);
    c.lineTo(4, 24);
    c.closePath();
  } else if (side === 'friendly') {
    c.rect(6, 10, 36, 28);
  } else {
    c.arc(24, 24, 18, 0, Math.PI * 2);
  }
  c.fill();
  c.stroke();
  c.beginPath();
  if (kind === 'tank') {
    c.ellipse(24, 25, 10, 6, 0, 0, Math.PI * 2);
    c.moveTo(24, 25);
    c.lineTo(35, 16);
  } else if (kind === 'naval_vessel') {
    c.moveTo(12, 25);
    c.lineTo(18, 32);
    c.lineTo(31, 32);
    c.lineTo(36, 25);
    c.closePath();
    c.moveTo(20, 25);
    c.lineTo(20, 17);
    c.lineTo(28, 17);
    c.lineTo(28, 25);
  } else if (kind === 'uav') {
    c.moveTo(10, 24);
    c.lineTo(38, 24);
    c.moveTo(24, 10);
    c.lineTo(24, 38);
    c.moveTo(18, 32);
    c.lineTo(30, 32);
  } else if (kind === 'armored_vehicle' || kind === 'support_vehicle') {
    c.rect(13, 19, 22, 11);
    c.moveTo(19, 32);
    c.arc(17, 32, 2, 0, Math.PI * 2);
    c.moveTo(33, 32);
    c.arc(31, 32, 2, 0, Math.PI * 2);
    if (kind === 'armored_vehicle') {
      c.moveTo(20, 19);
      c.lineTo(31, 13);
    }
  } else {
    c.moveTo(20, 20);
    c.lineTo(28, 28);
    c.moveTo(28, 20);
    c.lineTo(20, 28);
  }
  c.stroke();
  return c.getImageData(0, 0, 48, 48);
}

function SituationMap({
  entities,
  selected,
  onSelect,
  focus,
  view,
  onView,
  scenario,
  fitBounds,
  onFitted,
}: {
  entities: EntityView[];
  selected: string | null;
  onSelect: (id: string) => void;
  focus: number;
  view: { center: [number, number]; zoom: number; bearing: number };
  onView: (v: typeof view) => void;
  scenario?: Situation['scenario'];
  fitBounds: [number, number, number, number] | null;
  onFitted: () => void;
}) {
  const container = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null);
  const current = useRef({ entities, selected, onSelect, onView });
  current.current = { entities, selected, onSelect, onView };
  const [background, setBackground] = useState('지도 연결 중');
  const update = () => {
    const m = map.current;
    if (!m?.getSource('equipment')) return;
    const features: FeatureCollection<Geometry> = {
      type: 'FeatureCollection',
      features: current.current.entities.map((e) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [e.position.longitude, e.position.latitude] },
        properties: { ...e, icon: e.affiliation + '-' + e.kind },
      })),
    };
    (m.getSource('equipment') as GeoJSONSource).setData(features);
    (m.getSource('vectors') as GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: current.current.entities
        .filter((e) => e.displayVector)
        .map((e) => ({
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: [
              [e.position.longitude, e.position.latitude],
              [e.displayVector!.endPosition.longitude, e.displayVector!.endPosition.latitude],
            ],
          },
          properties: { entityId: e.entityId, affiliation: e.affiliation },
        })),
    });
    (m.getSource('vector-heads') as GeoJSONSource).setData({
      type: 'FeatureCollection',
      features: current.current.entities
        .filter((e) => e.displayVector)
        .map((e) => ({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [
              e.displayVector!.endPosition.longitude,
              e.displayVector!.endPosition.latitude,
            ],
          },
          properties: { icon: e.affiliation + '-arrow', bearing: e.bearingDegrees },
        })),
    });
    m.setFilter('selection', ['==', ['get', 'entityId'], current.current.selected ?? '']);
  };
  useEffect(() => {
    if (!container.current) return;
    const empty: StyleSpecification = {
      version: 8,
      sources: {},
      layers: [{ id: 'base', type: 'background', paint: { 'background-color': '#18232b' } }],
    };
    const m = new maplibregl.Map({
      container: container.current,
      style: empty,
      center: view.center,
      zoom: view.zoom,
      bearing: view.bearing,
      attributionControl: { compact: true },
      maxZoom: 18,
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'bottom-right');
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    m.on('style.load', () => {
      for (const side of ['friendly', 'hostile', 'unknown'])
        for (const kind of [
          'tank',
          'naval_vessel',
          'armored_vehicle',
          'support_vehicle',
          'uav',
          'unknown',
          'arrow',
        ])
          if (!m.hasImage(side + '-' + kind))
            m.addImage(side + '-' + kind, icon(side, kind), { pixelRatio: 2 });
      const data: FeatureCollection = { type: 'FeatureCollection', features: [] };
      m.addSource('vectors', { type: 'geojson', data });
      m.addSource('equipment', { type: 'geojson', data });
      m.addSource('vector-heads', { type: 'geojson', data });
      const color = [
        'match',
        ['get', 'affiliation'],
        'friendly',
        '#79b8f0',
        'hostile',
        '#f08d8d',
        '#b4bec7',
      ] as maplibregl.ExpressionSpecification;
      m.addLayer({
        id: 'vector-lines',
        type: 'line',
        source: 'vectors',
        paint: { 'line-color': color, 'line-width': 1.8, 'line-opacity': 0.85 },
      });
      m.addLayer({
        id: 'vector-head-symbols',
        type: 'symbol',
        source: 'vector-heads',
        layout: {
          'icon-image': ['get', 'icon'],
          'icon-rotate': ['get', 'bearing'],
          'icon-rotation-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-size': 0.7,
        },
      });
      m.addLayer({
        id: 'selection',
        type: 'circle',
        source: 'equipment',
        filter: ['==', ['get', 'entityId'], ''],
        paint: {
          'circle-radius': 21,
          'circle-color': 'transparent',
          'circle-stroke-color': '#e6edf3',
          'circle-stroke-width': 1.5,
        },
      });
      m.addLayer({
        id: 'equipment-symbols',
        type: 'symbol',
        source: 'equipment',
        layout: { 'icon-image': ['get', 'icon'], 'icon-allow-overlap': true, 'icon-size': 1.1 },
      });
      update();
    });
    m.on('click', 'equipment-symbols', (event) => {
      const id = event.features?.[0]?.properties?.entityId;
      if (id) current.current.onSelect(id);
    });
    m.on('mouseenter', 'equipment-symbols', () => {
      m.getCanvas().style.cursor = 'pointer';
    });
    m.on('mouseleave', 'equipment-symbols', () => {
      m.getCanvas().style.cursor = '';
    });
    m.on('moveend', () =>
      current.current.onView({
        center: [m.getCenter().lng, m.getCenter().lat],
        zoom: m.getZoom(),
        bearing: m.getBearing(),
      }),
    );
    m.on('error', () => setBackground('배경 지도 연결 지연 · 객체 데이터 유지'));
    m.on('render', () => {
      if (m.getLayer('equipment-symbols') && container.current?.parentElement) {
        container.current.parentElement.dataset.renderedEntities = String(
          m.queryRenderedFeatures({ layers: ['equipment-symbols'] }).length,
        );
        container.current.parentElement.dataset.basemapFeatures = String(
          m
            .queryRenderedFeatures()
            .filter((f) => !['equipment', 'vectors', 'vector-heads'].includes(f.source)).length,
        );
      }
    });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    fetch(import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/liberty', {
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) throw Error('map');
        return r.json();
      })
      .then((style: StyleSpecification) => {
        if (controller.signal.aborted) return;
        style.layers = style.layers.map((layer) => {
          if (layer.type === 'background')
            return { ...layer, paint: { 'background-color': '#18232b' } };
          if (layer.type === 'fill')
            return {
              ...layer,
              paint: {
                ...layer.paint,
                'fill-color': String(layer.id).includes('water') ? '#101b24' : '#222f36',
                'fill-opacity': 0.75,
              },
            };
          if (layer.type === 'line')
            return {
              ...layer,
              paint: { ...layer.paint, 'line-color': '#3b4a52', 'line-opacity': 0.5 },
            };
          if (layer.type === 'symbol')
            return {
              ...layer,
              paint: {
                ...layer.paint,
                'text-color': '#82939b',
                'text-halo-color': '#19232a',
                'text-halo-width': 1,
              },
            };
          return layer;
        });
        m.setStyle(style);
        setBackground('OpenStreetMap · 지리 지도');
      })
      .catch(() => setBackground('배경 지도 연결 지연 · 객체 데이터 유지'))
      .finally(() => clearTimeout(timer));
    return () => {
      controller.abort();
      clearTimeout(timer);
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(update, [entities, selected]);
  useEffect(() => {
    if (!fitBounds || !map.current) return;
    const [west, south, east, north] = fitBounds;
    map.current.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 55, duration: 0 },
    );
    onFitted();
  }, [fitBounds]);
  useEffect(() => {
    const e = entities.find((e) => e.entityId === selected);
    if (focus && e)
      map.current?.flyTo({
        center: [e.position.longitude, e.position.latitude],
        zoom: 11,
        duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 350,
      });
  }, [focus]);
  return (
    <div
      className="map-wrap"
      data-scenario-id={scenario?.scenarioId}
      data-map-longitude={view.center[0]}
      data-map-zoom={view.zoom}
    >
      <div ref={container} className="map-canvas" aria-label="지리 상황 지도" />
      <div className="map-heading">
        <span className="eyebrow">COMMON OPERATING PICTURE</span>
        <h2>{scenario?.name || '원천 상황 연결 중'}</h2>
        <div>
          <span className="live-dot" /> WGS84 · 실시간 원천 위치
        </div>
      </div>
      <button
        className="secondary map-overview"
        onClick={() => {
          if (scenario) {
            const [west, south, east, north] = scenario.initialBounds;
            map.current?.fitBounds(
              [
                [west, south],
                [east, north],
              ],
              { padding: 55, duration: 0 },
            );
          }
        }}
      >
        전체 보기
      </button>
      <div className="map-key">
        <span>
          <i className="key-friendly" />
          아군
        </span>
        <span>
          <i className="key-hostile" />
          적군
        </span>
        <span className="vector-key">↗ 현재 속도 × 30초 · 예측 아님</span>
      </div>
      <div className="map-provider">{background}</div>
    </div>
  );
}

export default function App({ mode }: { mode: 'c4i' | 'platform' }) {
  const isC4I = mode === 'c4i';
  const [situation, setSituation] = useState<Situation>({ entities: [] });
  const [selected, setSelected] = useState<string | null>(null),
    [side, setSide] = useState(''),
    [kind, setKind] = useState(''),
    [availability, setAvailability] = useState(''),
    [search, setSearch] = useState('');
  const [view, setView] = useState({
      center: [127.4, 38.1] as [number, number],
      zoom: 7,
      bearing: 0,
    }),
    [focus, setFocus] = useState(0);
  const [fitBounds, setFitBounds] = useState<[number, number, number, number] | null>(null);
  const scenarioRef = useRef('');
  useEffect(() => {
    if (!situation.scenario) return;
    const key = `${situation.scenarioId}:${situation.scenario.version}:${situation.epochId}`;
    if (scenarioRef.current === key) return;
    scenarioRef.current = key;
    setFitBounds([...situation.scenario.initialBounds]);
  }, [situation.scenarioId, situation.scenario?.version, situation.epochId]);
  const [connected, setConnected] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [runs, setRuns] = useState<Run[]>([]),
    [run, setRun] = useState<Run | null>(null),
    [tab, setTab] = useState('analysis'),
    [compare, setCompare] = useState<string | null>(null),
    [newCount, setNewCount] = useState(0);
  const [question, setQuestion] = useState(''),
    [conversation, setConversation] = useState<string | null>(() =>
      isC4I ? null : sessionStorage.getItem('platform.conversation'),
    ),
    [submitting, setSubmitting] = useState(false),
    [saving, setSaving] = useState(false);
  const [ready, setReady] = useState<{
    sourceConnected?: boolean;
    mcpConnected?: boolean;
    openaiConfigured?: boolean;
  }>({});
  const [eventText, setEventText] = useState('원천 이벤트를 기다리는 중'),
    [settings, setSettings] = useState(false);
  const [readToken, setReadToken] = useState(sessionStorage.getItem('c4i.readToken') || ''),
    [controlToken, setControlToken] = useState(sessionStorage.getItem('c4i.controlToken') || '');
  const [editAvailability, setEditAvailability] = useState('unknown'),
    [editMaintenance, setEditMaintenance] = useState('unknown'),
    [east, setEast] = useState('0'),
    [north, setNorth] = useState('0');
  const [mobileTab, setMobileTab] = useState('map');
  const activeRef = useRef<string | null>(null);
  activeRef.current = run?.runId ?? null;
  const conversationRef = useRef(conversation);
  conversationRef.current = conversation;
  const comparisonRun = runs.find((item) => item.runId === compare);
  const displayRuns = conversation
    ? runs
        .filter((item) => item.conversationId === conversation && item.trigger === 'user_query')
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
    : run
      ? [run]
      : [];
  const conversationBusy = displayRuns.some((item) => busy(item));
  useEffect(() => {
    if (isC4I) return;
    if (conversation) sessionStorage.setItem('platform.conversation', conversation);
    else sessionStorage.removeItem('platform.conversation');
  }, [conversation]);
  const visible = situation.entities.filter(
    (e) =>
      (!side || e.affiliation === side) &&
      (!kind || e.kind === kind) &&
      (!availability || e.availability === availability) &&
      (!search || `${e.entityId} ${e.label}`.toLowerCase().includes(search.toLowerCase())),
  );
  const entity = situation.entities.find((e) => e.entityId === selected);
  const request = async (path: string, init: RequestInit = {}, control = false) => {
    const token = control ? controlToken : readToken;
    const response = await fetch(path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(isC4I && token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    if (!response.ok) {
      if (response.status === 401 && isC4I) setSettings(true);
      const body = await response.json().catch(() => ({}));
      throw Error(body.detail || body.error || `연결 오류 ${response.status}`);
    }
    return response.json();
  };
  const refreshRuns = async () => {
    const data = await request('/api/v1/analyses');
    const currentConversation = conversationRef.current;
    let items: Run[] = data.items;
    if (currentConversation) {
      try {
        const history = await request(`/api/v1/conversations/${currentConversation}`);
        items = [
          ...items.filter((item) => item.conversationId !== currentConversation),
          ...history.items,
        ];
      } catch (error) {
        if (conversationRef.current === currentConversation) setError(String(error));
      }
    }
    if (conversationRef.current !== currentConversation) return;
    setRuns(items);
    const active =
      items.find((r) => r.runId === activeRef.current) ||
      (currentConversation
        ? items
            .filter((r) => r.conversationId === currentConversation)
            .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0]
        : undefined);
    if (active) setRun(active);
  };
  useEffect(() => {
    if (!isC4I && conversation) void refreshRuns().catch((error) => setError(String(error)));
  }, [conversation]);
  useEffect(() => {
    if (entity) {
      setEditAvailability(entity.availability);
      setEditMaintenance(entity.maintenanceStatus || 'unknown');
      setEast(String(entity.velocity.eastMps));
      setNorth(String(entity.velocity.northMps));
    }
  }, [selected]);
  useEffect(() => {
    let stopped = false;
    const abort = new AbortController();
    async function connect() {
      while (!stopped) {
        try {
          const initial = await request(isC4I ? '/api/v1/snapshot' : '/api/v1/situation');
          if (stopped) return;
          setSituation(initial);
          setConnected(true);
          setError('');
          if (!isC4I) await refreshRuns();
          const cursor = isC4I
            ? `epochId=${initial.epochId}&after=${initial.sequence}`
            : `after=${initial.platformCursor || 0}`;
          const response = await fetch('/api/v1/stream?' + cursor, {
            signal: abort.signal,
            headers: isC4I && readToken ? { Authorization: `Bearer ${readToken}` } : {},
          });
          if (!response.ok) throw Error('실시간 연결 실패');
          const reader = response.body!.getReader(),
            decoder = new TextDecoder();
          let buffer = '';
          while (!stopped) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const chunks = buffer.split('\n\n');
            buffer = chunks.pop() || '';
            for (const chunk of chunks) {
              const lines = chunk.split('\n');
              const data = lines.find((l) => l.startsWith('data: '));
              if (!data) continue;
              const payload = JSON.parse(data.slice(6));
              const type = lines.find((l) => l.startsWith('event: '))?.slice(7);
              if (isC4I) {
                setSituation(payload.snapshot);
                setEventText(
                  `${time(payload.occurredAt)} · ${payload.type} ${payload.entityId || ''}`,
                );
              } else if (type === 'situation') setSituation(payload);
              else if (type === 'analysis') {
                await refreshRuns();
                if (payload.runId !== activeRef.current) setNewCount((n) => n + 1);
              } else if (type === 'source_event')
                setEventText(
                  `${time(payload.occurredAt)} · ${payload.type} ${payload.entityId || ''}`,
                );
            }
          }
        } catch (e) {
          if (!stopped) {
            setConnected(false);
            setError(String(e));
          }
        }
        if (!stopped) await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }
    void connect();
    return () => {
      stopped = true;
      abort.abort();
    };
  }, [readToken]);
  useEffect(() => {
    if (isC4I) return;
    const refresh = () =>
      request('/ready')
        .then(setReady)
        .catch(() => {});
    void refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, []);
  const act = async (action: string) => {
    try {
      setSituation(await request(`/api/v1/simulation/${action}`, { method: 'POST' }, true));
      setError('');
    } catch (e) {
      setError(String(e));
    }
  };
  const saveEntity = async () => {
    try {
      await request(
        `/api/v1/entities/${selected}`,
        {
          method: 'PATCH',
          body: JSON.stringify({
            availability: editAvailability,
            maintenanceStatus: editMaintenance,
            velocity: { eastMps: Number(east), northMps: Number(north) },
          }),
        },
        true,
      );
      setNotice('변경 저장됨');
      setError('');
    } catch (e) {
      setError(String(e));
    }
  };
  const submit = async (text = question) => {
    if (!text.trim() || conversationBusy || submitting) return;
    setSubmitting(true);
    try {
      const created = await request('/api/v1/analyses', {
        method: 'POST',
        body: JSON.stringify({ question: text, conversationId: conversation }),
      });
      setRun(created);
      setRuns((items) => [...items.filter((item) => item.runId !== created.runId), created]);
      setConversation(created.conversationId);
      setQuestion('');
      setTab('analysis');
      setMobileTab('analysis');
      setError('');
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };
  const choose = async (runId: string, courseId: string) => {
    setSaving(true);
    try {
      const updated = await request(`/api/v1/analyses/${runId}/selection`, {
        method: 'PUT',
        body: JSON.stringify({ courseId }),
      });
      setRuns((items) => items.map((item) => (item.runId === runId ? updated : item)));
      setRun((active) => (active?.runId === runId ? updated : active));
      setError('');
      setNotice('선택 저장됨');
    } catch (e) {
      setError(`방책 선택 실패: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };
  const statusConnected = isC4I ? connected : connected && ready.sourceConnected;
  const selectEntity = (id: string) => {
    setSelected(id);
    setNotice('');
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark">
          <Layers size={18} />
        </div>
        <strong>{isC4I ? 'MOCK C4I' : 'BATTLEFIELD'}</strong>
        <span className="top-divider" />
        <span className="workspace-name">{isC4I ? '모의 지휘통제' : 'Intelligence Workspace'}</span>
        <span className="environment">SIMULATION</span>
        <div className="top-status">
          <span className={statusConnected ? 'live-dot' : 'offline-dot'} />
          {statusConnected ? 'C4I 연결' : 'C4I 연결 대기'}
          <span className="time">{time(situation.sourceTime)} KST</span>
          <button
            className="icon-button"
            aria-label="연결 설정"
            onClick={() => setSettings(!settings)}
          >
            <Settings size={16} />
          </button>
        </div>
      </header>
      {settings && (
        <div className="settings-panel">
          <div className="panel-heading">
            연결 설정
            <button
              className="icon-button"
              onClick={() => setSettings(false)}
              aria-label="설정 닫기"
            >
              <X size={16} />
            </button>
          </div>
          {isC4I ? (
            <>
              <label>
                조회 토큰
                <input
                  type="password"
                  value={readToken}
                  onChange={(e) => {
                    setReadToken(e.target.value);
                    sessionStorage.setItem('c4i.readToken', e.target.value);
                  }}
                />
              </label>
              <label>
                제어 토큰
                <input
                  type="password"
                  value={controlToken}
                  onChange={(e) => {
                    setControlToken(e.target.value);
                    sessionStorage.setItem('c4i.controlToken', e.target.value);
                  }}
                />
              </label>
              <p>설정된 서버에서만 필요합니다. 이 탭에만 보관합니다.</p>
            </>
          ) : (
            <>
              <p>
                원천 수집 {ready.sourceConnected ? '연결' : '대기'} · MCP{' '}
                {ready.mcpConnected ? '연결 확인됨' : '미확인'}
              </p>
              <p>분석 모델 {ready.openaiConfigured ? '설정됨' : '연결 설정 필요'}</p>
            </>
          )}
        </div>
      )}
      <div className="mobile-tabs">
        <button onClick={() => setMobileTab('map')}>상황 지도</button>
        <button onClick={() => setMobileTab('analysis')}>{isC4I ? '객체 제어' : '분석'}</button>
      </div>
      <div className={`workspace ${compare ? 'comparing' : ''}`}>
        <nav className="rail">
          <button
            className={!compare ? 'active' : ''}
            title="상황판"
            aria-label="상황판"
            onClick={() => setCompare(null)}
          >
            <MapIcon size={20} />
          </button>
          {!isC4I && (
            <button
              title="분석 이력"
              aria-label="분석 이력"
              onClick={() => {
                setCompare(null);
                setTab('history');
                setNewCount(0);
                setMobileTab('analysis');
              }}
            >
              <History size={20} />
              {newCount > 0 && <i />}
            </button>
          )}
          <span className="rail-spacer" />
          <span className="rail-bottom">
            POC
            <br />
            01
          </span>
        </nav>
        {comparisonRun?.result?.courses ? (
          <section className="comparison">
            <div className="comparison-head">
              <div>
                <span className="eyebrow">COURSES OF ACTION</span>
                <h1>세 가지 방책 비교</h1>
                <p>{comparisonRun.result.answer}</p>
                <span className="meta">
                  분석 기준 {time(comparisonRun.sourceContext?.sourceTime)} · 현재 원천{' '}
                  {time(situation.sourceTime)}
                </span>
              </div>
              <button className="secondary" onClick={() => setCompare(null)}>
                <ArrowLeft size={14} />
                분석으로 돌아가기
              </button>
            </div>
            <div className="course-grid">
              {comparisonRun.result.courses.map((course, i) => (
                <article
                  data-testid="course-column"
                  className={`course ${comparisonRun.selectedCourseId === course.id ? 'chosen' : ''}`}
                  key={course.id}
                >
                  <div className="course-title">
                    <span className="eyebrow">방책 {String(i + 1).padStart(2, '0')}</span>
                    <h2>{course.title}</h2>
                  </div>
                  <div className="course-body">
                    <section>
                      <h3>요약</h3>
                      <p>{course.summary}</p>
                    </section>
                    <section>
                      <h3>근거</h3>
                      {course.evidenceIds.map((id) => (
                        <code key={id}>{id}</code>
                      ))}
                    </section>
                    <section>
                      <h3>기대 효과</h3>
                      {course.expectedEffects.map((text, j) => (
                        <p key={j}>{text}</p>
                      ))}
                    </section>
                    <section>
                      <h3>위험·제약</h3>
                      {course.risksAndConstraints.map((text, j) => (
                        <p key={j}>{text}</p>
                      ))}
                    </section>
                  </div>
                  <button
                    className={
                      comparisonRun.selectedCourseId === course.id
                        ? 'primary selected-course'
                        : 'secondary'
                    }
                    aria-label={`방책 ${i + 1} 선택`}
                    disabled={saving}
                    onClick={() => void choose(comparisonRun.runId, course.id)}
                  >
                    {comparisonRun.selectedCourseId === course.id ? (
                      <>
                        <Check size={15} />
                        선택됨
                      </>
                    ) : (
                      <>
                        이 방책 선택
                        <ArrowUpRight size={15} />
                      </>
                    )}
                  </button>
                </article>
              ))}
            </div>
            <div className="comparison-foot" role="status">
              {error && <p className="error-message">{error}</p>}
              {saving ? '선택 저장 중' : notice || '세 방책을 검토하고 하나를 선택하세요.'}
            </div>
          </section>
        ) : (
          <>
            <aside className="objects-panel">
              <div className="panel-heading">
                <span>객체 탐색</span>
                <span className="small-count">{situation.entities.length}</span>
              </div>
              {!!situation.scenario?.zones.length && (
                <select
                  className="zone-explorer"
                  aria-label="시연 구역 이동"
                  defaultValue=""
                  onChange={(e) => {
                    const zone = situation.scenario?.zones.find(
                      (zone) => zone.id === e.target.value,
                    );
                    if (zone) setFitBounds([...zone.bounds]);
                  }}
                >
                  <option value="">시연 구역 이동</option>
                  {situation.scenario.zones.map((zone) => (
                    <option key={zone.id} value={zone.id}>
                      {zone.name}
                    </option>
                  ))}
                </select>
              )}
              <div className="search-box">
                <Search size={14} />
                <input
                  aria-label="객체 검색"
                  placeholder="식별자 또는 이름 검색"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="filters">
                <select
                  aria-label="소속 필터"
                  value={side}
                  onChange={(e) => setSide(e.target.value)}
                >
                  <option value="">모든 소속</option>
                  <option value="friendly">아군</option>
                  <option value="hostile">적군</option>
                  <option value="unknown">미확인</option>
                </select>
                <select
                  aria-label="유형 필터"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  <option value="">모든 유형</option>
                  <option value="tank">탱크</option>
                  <option value="naval_vessel">함정</option>
                  <option value="armored_vehicle">장갑차</option>
                  <option value="support_vehicle">지원 차량</option>
                  <option value="uav">무인기</option>
                  <option value="unknown">미확인</option>
                </select>
                <select
                  aria-label="가용 필터"
                  value={availability}
                  onChange={(e) => setAvailability(e.target.value)}
                >
                  <option value="">모든 가용 상태</option>
                  <option value="available">가용</option>
                  <option value="unavailable">가용 불가</option>
                  <option value="unknown">미확인</option>
                </select>
                {(side || kind || availability || search) && (
                  <button
                    className="text-button"
                    onClick={() => {
                      setSide('');
                      setKind('');
                      setAvailability('');
                      setSearch('');
                    }}
                  >
                    초기화
                  </button>
                )}
              </div>
              <div className="list-caption">
                <span>등록된 객체</span>
                <span data-testid="entity-count">전체 일치 {visible.length}</span>
              </div>
              <div className="entity-list">
                {visible.map((e) => (
                  <button
                    key={e.entityId}
                    className={`entity-row ${selected === e.entityId ? 'selected' : ''}`}
                    onClick={() => selectEntity(e.entityId)}
                    aria-label={`${e.entityId} ${labels[e.affiliation]} ${labels[e.kind]}`}
                  >
                    <span className={`entity-symbol ${e.affiliation}`}>
                      {e.kind === 'naval_vessel' ? (
                        <Ship size={14} />
                      ) : e.kind === 'support_vehicle' ? (
                        <Layers size={14} />
                      ) : e.kind === 'uav' ? (
                        <Crosshair size={14} />
                      ) : (
                        <Target size={14} />
                      )}
                    </span>
                    <span className="entity-text">
                      <strong>{e.entityId}</strong>
                      <small>
                        {labels[e.affiliation]} · {labels[e.kind]} · {labels[e.availability]}
                      </small>
                      {selected === e.entityId && (
                        <span className="entity-attributes" data-testid="entity-attributes">
                          <small>
                            부대 {e.unitId || '미상'} · {e.subtype || '분류 미상'}
                          </small>
                          <small>
                            {labels[e.maintenanceStatus || 'unknown']} ·{' '}
                            {time(e.observedAt || undefined)}
                          </small>
                          <small>출처 {e.source || '미상'}</small>
                        </span>
                      )}
                    </span>
                    <ChevronRight size={13} />
                  </button>
                ))}
                {!visible.length && <p className="empty">조건에 맞는 객체가 없습니다.</p>}
              </div>
              <div className="objects-footer">
                <span className="live-dot" />{' '}
                {situation.running ? '이동 갱신 중' : '원천 상태 유지'}
                <span>REV {String(situation.revision || 0).padStart(4, '0')}</span>
              </div>
            </aside>
            <main className={`map-main ${mobileTab === 'analysis' ? 'mobile-hidden' : ''}`}>
              <SituationMap
                entities={visible}
                selected={selected}
                onSelect={selectEntity}
                focus={focus}
                view={view}
                onView={setView}
                scenario={situation.scenario}
                fitBounds={fitBounds}
                onFitted={() => setFitBounds(null)}
              />
              <div className="map-bottom-panel">
                <span className="eyebrow">SITUATION SUMMARY</span>
                <div>
                  <strong>
                    {situation.entities.filter((e) => e.affiliation === 'friendly').length}
                    <small>아군 객체</small>
                  </strong>
                  <strong>
                    {situation.entities.filter((e) => e.affiliation === 'hostile').length}
                    <small>적군 객체</small>
                  </strong>
                  <strong>
                    {
                      situation.entities.filter(
                        (e) =>
                          e.kind === 'tank' &&
                          e.affiliation === 'friendly' &&
                          e.availability === 'available',
                      ).length
                    }
                    <small>가용 아군 탱크</small>
                  </strong>
                </div>
              </div>
            </main>
            <aside className={`analysis-panel ${mobileTab === 'map' ? 'mobile-hidden' : ''}`}>
              {isC4I ? (
                <>
                  <div className="panel-heading">
                    <span>시뮬레이션 제어</span>
                    <Radio size={15} />
                  </div>
                  <div className="simulation-controls">
                    <button
                      className="primary"
                      onClick={() => void act(situation.running ? 'pause' : 'start')}
                    >
                      {situation.running ? <Pause size={14} /> : <Play size={14} />}{' '}
                      {situation.running ? '일시 정지' : '이동 시작'}
                    </button>
                    <button className="secondary" onClick={() => void act('reset')}>
                      <RefreshCw size={14} />
                      초기화
                    </button>
                  </div>
                  <div className="simulation-meta">
                    <span>SIM TIME</span>
                    <code>{String(situation.simulationTime || 0).padStart(5, '0')} s</code>
                    <span>UPDATE</span>
                    <code>1 SECOND</code>
                  </div>
                  {entity ? (
                    <div className="object-detail">
                      <div className="section-label">선택 객체</div>
                      <h2>{entity.entityId}</h2>
                      <p>
                        {labels[entity.affiliation]} · {labels[entity.kind]}
                      </p>
                      <dl>
                        <dt>경도 / 위도</dt>
                        <dd>
                          {entity.position.longitude.toFixed(5)} /{' '}
                          {entity.position.latitude.toFixed(5)}
                        </dd>
                        <dt>속도 / 방향</dt>
                        <dd>
                          {entity.speedMps.toFixed(1)} m/s ·{' '}
                          {entity.bearingDegrees === null
                            ? '정지'
                            : entity.bearingDegrees.toFixed(0) + '°'}
                        </dd>
                        <dt>운용 상태</dt>
                        <dd>{labels[entity.status]}</dd>
                        <dt>부대 / 세부 유형</dt>
                        <dd>
                          {entity.unitId || '미상'} / {entity.subtype || '미상'}
                        </dd>
                        <dt>정비 상태</dt>
                        <dd>{labels[entity.maintenanceStatus || 'unknown']}</dd>
                        <dt>관측 시각 / 출처</dt>
                        <dd>
                          {time(entity.observedAt || undefined)} / {entity.source || '미상'}
                        </dd>
                      </dl>
                      <label>
                        정비 상태
                        <select
                          aria-label="정비 상태 변경"
                          value={editMaintenance}
                          onChange={(e) => setEditMaintenance(e.target.value)}
                        >
                          <option value="serviceable">정비 정상</option>
                          <option value="maintenance">정비 중</option>
                          <option value="unknown">미확인</option>
                        </select>
                      </label>
                      <label>
                        가용 상태
                        <select
                          aria-label="가용 상태 변경"
                          value={editAvailability}
                          onChange={(e) => setEditAvailability(e.target.value)}
                        >
                          <option value="available">가용</option>
                          <option value="unavailable">가용 불가</option>
                          <option value="unknown">미확인</option>
                        </select>
                      </label>
                      <div className="velocity-fields">
                        <label>
                          동쪽 속도 m/s
                          <input
                            type="number"
                            min="-200"
                            max="200"
                            value={east}
                            onChange={(e) => setEast(e.target.value)}
                          />
                        </label>
                        <label>
                          북쪽 속도 m/s
                          <input
                            type="number"
                            min="-200"
                            max="200"
                            value={north}
                            onChange={(e) => setNorth(e.target.value)}
                          />
                        </label>
                      </div>
                      <button className="primary full" onClick={() => void saveEntity()}>
                        변경 적용
                      </button>
                      <div className="success-note" role="status">
                        {notice}
                      </div>
                      <button className="text-button" onClick={() => setFocus((n) => n + 1)}>
                        <Crosshair size={13} />
                        지도에서 보기
                      </button>
                    </div>
                  ) : (
                    <div className="placeholder-block">
                      <Crosshair size={24} />
                      <h3>객체를 선택하세요</h3>
                      <p>
                        목록 또는 지도에서 객체를 선택해
                        <br />
                        가용 상태와 이동 벡터를 변경합니다.
                      </p>
                    </div>
                  )}
                  <div className="operator-note">
                    <Shield size={15} />
                    <p>
                      외부 C4I를 모사하는 독립 시스템입니다.
                      <br />
                      분석 플랫폼 없이 실행할 수 있습니다.
                    </p>
                  </div>
                </>
              ) : (
                <>
                  <div className="panel-tabs">
                    <button
                      className={tab === 'analysis' ? 'active' : ''}
                      onClick={() => setTab('analysis')}
                    >
                      상황 분석
                    </button>
                    <button
                      className={tab === 'history' ? 'active' : ''}
                      onClick={() => {
                        setTab('history');
                        setNewCount(0);
                      }}
                    >
                      실행 이력{newCount > 0 && <span>{newCount}</span>}
                    </button>
                    <button
                      className="icon-button"
                      aria-label="새 대화"
                      title="새 대화"
                      onClick={() => {
                        setConversation(null);
                        setRun(null);
                        setCompare(null);
                        setTab('analysis');
                      }}
                    >
                      <RefreshCw size={14} />
                    </button>
                  </div>
                  <div className="analysis-body">
                    {tab === 'history' ? (
                      <>
                        <div className="section-label">ANALYSIS HISTORY</div>
                        {runs.map((r) => (
                          <button
                            className="history-row"
                            key={r.runId}
                            onClick={() => {
                              setRun(r);
                              setConversation(r.conversationId);
                              setTab('analysis');
                            }}
                          >
                            <span className="meta">
                              {r.trigger === 'c4i_event' ? '이벤트 자동 분석' : '사용자 질의'} ·{' '}
                              {time(r.createdAt)}
                            </span>
                            <strong>
                              {r.trigger === 'c4i_event' ? r.sourceEvent?.type : r.question}
                            </strong>
                            <span className={`state-badge ${r.status}`}>
                              {labels[r.status] || r.status}
                            </span>
                          </button>
                        ))}
                        {!runs.length && <p className="empty">아직 분석 이력이 없습니다.</p>}
                      </>
                    ) : displayRuns.length ? (
                      displayRuns.map((run) => (
                        <article className="chat-turn" data-testid="chat-turn" key={run.runId}>
                          <div className="run-meta">
                            <span className="eyebrow">
                              {run.trigger === 'c4i_event' ? 'EVENT ANALYSIS' : 'USER QUERY'}
                            </span>
                            <span className={`state-badge ${run.status}`}>
                              {labels[run.status] || run.status}
                            </span>
                          </div>
                          <div className="question-block">
                            {run.trigger === 'c4i_event'
                              ? `C4I 이벤트 · ${run.sourceEvent?.type}`
                              : run.question}
                          </div>
                          {busy(run) && (
                            <div className="running-note">
                              <Activity size={15} />
                              상황 분석 Agent가 정보를 확인하고 있습니다.
                            </div>
                          )}
                          {run.result && (
                            <>
                              <div className="result-heading">
                                <span className="section-label">분석 결과</span>
                                <span className="meta">
                                  {time(run.sourceContext?.sourceTime || run.updatedAt)}
                                </span>
                              </div>
                              <p className="answer-text">{run.result.answer}</p>
                              {run.result.findings.map((f, i) => (
                                <div className="finding" key={i}>
                                  <span className="meta">
                                    {f.category === 'fact'
                                      ? '관측'
                                      : f.category === 'inference'
                                        ? '분석'
                                        : '가정'}
                                  </span>
                                  <p>{f.text}</p>
                                </div>
                              ))}
                              {run.result.limitations.length > 0 && (
                                <div className="limitations">
                                  <span>분석 범위·한계</span>
                                  {run.result.limitations.map((s, i) => (
                                    <p key={i}>{s}</p>
                                  ))}
                                </div>
                              )}
                              {run.result.courses && (
                                <button
                                  className="primary full compare-button"
                                  onClick={() => {
                                    setCompare(run.runId);
                                    setNotice('');
                                  }}
                                >
                                  방책 3개 비교
                                  <ArrowUpRight size={15} />
                                </button>
                              )}
                              {run.selectedCourseId && (
                                <div className="selected-course-note" data-testid="selected-course">
                                  <Check size={14} /> 선택한 방책:{' '}
                                  {run.result.courses?.find(
                                    (course) => course.id === run.selectedCourseId,
                                  )?.title || run.selectedCourseId}
                                </div>
                              )}
                            </>
                          )}
                          {run.error && <div className="error-message">{run.error}</div>}
                          <details className="trace">
                            <summary>
                              실행 상세<span>{run.toolCalls.length} TOOL CALLS</span>
                            </summary>
                            <div className="trace-agent">상황 분석 Agent · 단일 loop</div>
                            {run.toolCalls.map((c, i) => (
                              <details className="tool-call" key={c.callId + i}>
                                <summary>
                                  <span
                                    className={
                                      c.status === 'completed' ? 'live-dot' : 'offline-dot'
                                    }
                                  />
                                  <code>{c.name}</code>
                                  <span>{labels[c.status] || c.status}</span>
                                </summary>
                                <span className="meta">
                                  {time(c.startedAt)} → {time(c.endedAt)}
                                </span>
                                <pre>
                                  {JSON.stringify(
                                    { input: c.arguments, output: c.response },
                                    null,
                                    2,
                                  )}
                                </pre>
                              </details>
                            ))}
                            {!run.toolCalls.length && <p className="meta">도구 호출 없음</p>}
                          </details>
                          <details className="trace">
                            <summary>
                              근거 데이터<span>{run.evidence.length} SOURCES</span>
                            </summary>
                            {run.evidence.map((e) => (
                              <details key={e.evidenceId} className="evidence-item">
                                <summary>
                                  {e.evidenceId}
                                  <small>{e.tool}</small>
                                </summary>
                                <pre>{JSON.stringify(e.data, null, 2)}</pre>
                              </details>
                            ))}
                          </details>
                          <div className="run-id">RUN {run.runId.slice(0, 12)}</div>
                        </article>
                      ))
                    ) : (
                      <>
                        <div className="analysis-intro">
                          <span className="eyebrow">SITUATION INTELLIGENCE</span>
                          <h2>
                            상황을 묻고,
                            <br />
                            근거를 확인하세요.
                          </h2>
                          <p>
                            원천 C4I의 객체와 변화를 조회해
                            <br />
                            현재 상황을 함께 검토합니다.
                          </p>
                        </div>
                        <div className="suggestions">
                          <span className="section-label">질의 시작하기</span>
                          {[
                            '가용 아군 탱크 보여줘',
                            '적 탱크는 몇 대야?',
                            '함정의 가용 상태별 수를 알려줘',
                          ].map((q) => (
                            <button key={q} onClick={() => void submit(q)}>
                              {q}
                              <ArrowUpRight size={14} />
                            </button>
                          ))}
                        </div>
                        <div className="intro-rule">
                          <span>01</span>
                          <p>상황 조회</p>
                          <span>02</span>
                          <p>근거 확인</p>
                          <span>03</span>
                          <p>방책 비교</p>
                        </div>
                        {ready.openaiConfigured === false && (
                          <p className="model-note">분석 모델 연결 설정이 필요합니다.</p>
                        )}
                      </>
                    )}
                  </div>
                  <div className="query-composer">
                    <textarea
                      aria-label="분석 질의"
                      placeholder="상황에 대해 질문하세요…"
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                          e.preventDefault();
                          void submit();
                        }
                      }}
                    />
                    <div>
                      <span>단일 Agent · MCP 근거 조회</span>
                      <button
                        className="send-button"
                        aria-label="질의 실행"
                        disabled={!question.trim() || conversationBusy || submitting}
                        onClick={() => void submit()}
                      >
                        <Send size={15} />
                      </button>
                    </div>
                  </div>
                </>
              )}
            </aside>
          </>
        )}
      </div>
      <footer className="event-strip">
        <Activity size={13} />
        <span className="event-label">EVENT STREAM</span>
        <span>{error || eventText}</span>
        <span className="footer-right">
          모의 데이터 · {isC4I ? 'C4I SOURCE' : 'ANALYTICAL PLATFORM'} · KST
        </span>
      </footer>
    </div>
  );
}
