import { useCallback, useEffect, useRef, useState } from 'react';
import { api, getToken, onSessionExpired, refusalReason, setToken } from './api/client';
import Masthead from './components/Masthead';
import Copilot from './components/Copilot';
import SignIn from './components/SignIn';
import SideNav, { PAGES, allowsPage } from './components/SideNav';
import { Drawer, Toast } from './components/Overlays';
import { Loading, Status, Tag } from './components/ui';
import { label } from './lib/format';

import OperationsDashboard from './pages/OperationsDashboard';
import PatientJourney from './pages/PatientJourney';
import ReadinessReview from './pages/ReadinessReview';
import PatientTimeline from './pages/PatientTimeline';
import JourneyPlanner from './pages/JourneyPlanner';
import PatientOnboarding from './pages/PatientOnboarding';
import ManufacturingSchedule, { SagaDetail } from './pages/ManufacturingSchedule';
import ShipmentTracking, { ShipmentDetail } from './pages/ShipmentTracking';
import DocumentIntake from './pages/DocumentIntake';
import AiAssistants, { AgentResultDetail } from './pages/AiAssistants';
import ReadinessDetail from './pages/ReadinessDetail';
import ReviewerPacket from './pages/ReviewerPacket';
import StageAction from './pages/StageAction';
import { PatientIdentity, DocumentSecurity } from './pages/GovernancePages';
import { AuditTrail, ExceptionQueue, SiteCapacity } from './pages/SimplePages';

export default function App() {
  const [session, setSession] = useState(null);
  const [signInNotice, setSignInNotice] = useState('');
  const [health, setHealth] = useState(null);
  const [page, setPage] = useState('dashboard');
  const [patientKey, setPatientKey] = useState('P-00005');
  const [reloadKey, setReloadKey] = useState(0);

  const [drawer, setDrawer] = useState(null);
  const [toast, setToast] = useState(null);
  const [navOpen, setNavOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(
    () => localStorage.getItem('cellchain.nav') === 'collapsed',
  );
  const toastTimer = useRef(null);

  const toggleCollapse = () => setNavCollapsed((v) => {
    localStorage.setItem('cellchain.nav', v ? 'expanded' : 'collapsed');
    return !v;
  });

  const notify = useCallback((next) => {
    setToast(next);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 7000);
  }, []);

  useEffect(() => {
    onSessionExpired((reason) => {
      setSession(null);
      setSignInNotice(reason);
    });
  }, []);

  useEffect(() => {
    api.anonymous.get('/api/health').then((r) => setHealth(r.data));
  }, []);

  // A token kept from a previous page load is only trusted once the server confirms it.
  useEffect(() => {
    if (session || !getToken()) return;
    api.get('/api/auth/me').then(({ ok, data }) => {
      if (ok) setSession({ user: data.user, role: data.role });
    });
  }, [session]);

  const signIn = (payload) => {
    setToken(payload.token);
    setSignInNotice('');
    setSession({ user: payload.user, role: payload.role });
    setPage('dashboard');
    setReloadKey((n) => n + 1);
  };

  const signOut = async () => {
    await api.post('/api/auth/logout');
    setToken('');
    setDrawer(null);
    setSession(null);
    setSignInNotice('You have been signed out.');
  };

  const can = (action) => Boolean(session?.role?.actions?.includes(action));

  // A role that loses access to a page must not be left sitting on it.
  useEffect(() => {
    if (session && !allowsPage(PAGES[page], can)) setPage('dashboard');
  });   // eslint-disable-line react-hooks/exhaustive-deps

  const navigate = (next) => {
    setPage(next);
    setDrawer(null);
    setNavOpen(false);
  };

  /* ------------------------------- drawers ------------------------------- */

  const openReadiness = async (key) => {
    setPatientKey(key);
    setDrawer({ kind: 'readiness', title: key, eyebrow: 'Readiness detail', payload: null });
    const { ok, data } = await api.get(`/api/journeys/${key}`);
    if (!ok) {
      setDrawer(null);
      notify({ tone: 'fail', title: 'Unavailable', body: refusalReason(data) });
      return;
    }
    setDrawer({
      kind: 'readiness',
      eyebrow: 'Readiness detail',
      title: key,
      meta: (
        <div className="row">
          <Status value={data.readiness.readiness} />
          <Tag>{data.readiness.policy_version}</Tag>
          <Tag>Governed state: {label(data.journey.state)}</Tag>
          <Tag>Authority: {data.readiness.required_authority}</Tag>
        </div>
      ),
      payload: data,
    });
  };

  const openPacket = (key) => {
    setPatientKey(key);
    setDrawer({
      kind: 'packet',
      eyebrow: 'Reviewer packet',
      title: key,
      meta: <Tag>Evidence · the rule that fired · decision</Tag>,
      payload: { lotId: key },
    });
  };

  const openAction = async (key, stage) => {
    setPatientKey(key);
    setDrawer({ kind: 'action', eyebrow: 'Required action', title: stage.name, payload: null });
    const { ok, data } = await api.get(`/api/workflow/${key}/actions/${stage.stage_id}`);
    if (!ok) {
      setDrawer(null);
      notify({ tone: 'fail', title: 'Unavailable', body: refusalReason(data) });
      return;
    }
    setDrawer({
      kind: 'action',
      eyebrow: `Required action — ${key}`,
      title: `${data.stage_id} · ${data.stage}`,
      meta: (
        <div className="row">
          <Status value={data.status} />
          <Tag>Authority: {data.authority}</Tag>
        </div>
      ),
      payload: data,
    });
  };

  const openShipment = async (shipmentId) => {
    setDrawer({ kind: 'shipment', eyebrow: 'Shipment', title: shipmentId, payload: null });
    const { ok, data } = await api.get(`/api/tracking/${shipmentId}`);    if (!ok) {
      setDrawer(null);
      notify({ tone: 'fail', title: 'Unavailable', body: refusalReason(data) });
      return;
    }
    setDrawer({
      kind: 'shipment',
      eyebrow: `${label(data.direction)} shipment`,
      title: shipmentId,
      meta: (
        <div className="row">
          <Status value={data.status} />
          <Tag>{data.origin} → {data.destination}</Tag>
          <Tag>Chain of identity {data.coi_id}</Tag>
          {data.batch_id && <Tag>{data.batch_id}</Tag>}
        </div>
      ),
      payload: data,
    });
  };

  const runAgent = async (agentId, subject) => {
    const { ok, data } = await api.post(`/api/agents/${agentId}/invoke`, { subject });
    if (!ok) {
      notify({ tone: 'fail', title: 'Assistant refused', body: refusalReason(data) });
      return;
    }
    setDrawer({
      kind: 'agent',
      eyebrow: 'AI assistant — advisory only',
      title: data.result.agent_id,
      payload: data.result,
    });
  };

  const showSaga = (payload) => {
    setDrawer({
      kind: 'saga',
      eyebrow: 'Reservation workflow',
      title: payload.saga.saga_id,
      payload,
    });
  };

  /* -------------------------------- pages -------------------------------- */

  const meta = PAGES[page];

  const renderPage = () => {
    switch (page) {
      case 'dashboard': return <OperationsDashboard key={reloadKey} />;
      case 'journey': return (
        <PatientJourney
          key={reloadKey}
          patientKey={patientKey}
          onPatientKeyChange={setPatientKey}
          onOpenReadiness={openReadiness}
          onOpenAction={openAction}
          onRunAgent={runAgent}
        />
      );
      case 'timeline': return <PatientTimeline key={`${reloadKey}-${patientKey}`} patientKey={patientKey} />;
      case 'planner': return <JourneyPlanner key={reloadKey} />;
      case 'onboarding': return <PatientOnboarding key={reloadKey} notify={notify} />;
      case 'readiness': return <ReadinessReview key={reloadKey} onOpenReadiness={openReadiness} />;
      case 'exceptions': return <ExceptionQueue key={reloadKey} />;
      case 'schedule': return <ManufacturingSchedule key={reloadKey} notify={notify} onShowSaga={showSaga} can={can} />;
      case 'shipments': return <ShipmentTracking key={reloadKey} onOpenShipment={openShipment} />;
      case 'intake': return <DocumentIntake key={reloadKey} notify={notify} roleName={session.role.name} />;
      case 'identity': return <PatientIdentity key={reloadKey} notify={notify} can={can} />;
      case 'capacity': return <SiteCapacity key={reloadKey} />;
      case 'assistants': return <AiAssistants key={reloadKey} onRunAgent={runAgent} patientKey={patientKey} />;
      case 'security': return <DocumentSecurity key={reloadKey} notify={notify} />;
      case 'audit': return <AuditTrail key={reloadKey} />;
      default: return null;
    }
  };

  const renderDrawer = () => {
    if (!drawer) return null;
    if (!drawer.payload) return <Loading />;
    switch (drawer.kind) {
      case 'readiness': return (
        <ReadinessDetail
          detail={drawer.payload}
          notify={notify}
          onRunAgent={runAgent}
          can={can}
          onOpenPacket={openPacket}
          onRefresh={() => openReadiness(drawer.title)}
        />
      );
      case 'packet': return (
        <ReviewerPacket
          lotId={drawer.payload.lotId}
          notify={notify}
          onRefresh={() => setReloadKey((n) => n + 1)}
        />
      );
      case 'shipment': return <ShipmentDetail shipment={drawer.payload} onRunAgent={runAgent} />;
      case 'action': return (
        <StageAction
          plan={drawer.payload}
          notify={notify}
          onRunAgent={runAgent}
          onOpenReadiness={openReadiness}
          onRefresh={() => {
            setReloadKey((n) => n + 1);   // the journey behind the drawer must show the new record
            openAction(drawer.payload.patient_key, {
              stage_id: drawer.payload.stage_id,
              name: drawer.payload.stage,
            });
          }}
        />
      );
      case 'agent': return <AgentResultDetail result={drawer.payload} />;
      case 'saga': return <SagaDetail payload={drawer.payload} />;
      default: return null;
    }
  };

  if (!health) return <div className="loading">Connecting to the orchestration service…</div>;
  if (!session) return <SignIn onSignedIn={signIn} notice={signInNotice} />;

  return (
    <div className="app">
      <Masthead
        user={session.user}
        role={session.role}
        onSignOut={signOut}
        onToggleNav={() => setNavOpen((v) => !v)}
        environment={health.synthetic ? 'Synthetic environment' : 'Production'}
      />

      <div className="frame">
        <div
          className={`navscrim${navOpen ? ' navscrim--open' : ''}`}
          onClick={() => setNavOpen(false)}
        />
        <SideNav
          activePage={page}
          onNavigate={navigate}
          can={can}
          open={navOpen}
          collapsed={navCollapsed}
          onToggleCollapse={toggleCollapse}
        />

        <main className="main">
          <div className="subheader">
            <div className="subheader__inner">
              <div className="subheader__text">
                <div className="subheader__eyebrow">{meta.eyebrow}</div>
                <h1>{meta.title}</h1>
                <p className="subheader__lede">{meta.lede}</p>
              </div>
              <div className="subheader__actions">
                <Tag>Policy {health.policy_version}</Tag>
                <Status value={health.llm_configured ? 'UNKNOWN' : 'PASS'}>
                  {health.llm_configured ? 'Model configured' : 'Deterministic control plane'}
                </Status>
              </div>
            </div>
          </div>

          <div className="page">{renderPage()}</div>
        </main>
      </div>

      <Drawer
        open={Boolean(drawer)}
        eyebrow={drawer?.eyebrow}
        title={drawer?.title || ''}
        meta={drawer?.meta}
        onClose={() => setDrawer(null)}
      >
        {renderDrawer()}
      </Drawer>

      <Toast toast={toast} onDismiss={() => setToast(null)} />

      <Copilot
        patientKey={patientKey}
        pageTitle={meta.title}
        roleName={session.role.name}
      />
    </div>
  );
}
