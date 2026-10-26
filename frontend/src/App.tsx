import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Bell,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  CreditCard,
  LayoutDashboard,
  Plus,
  Send,
  Settings2,
  ShieldCheck,
  Search,
  ShoppingBag,
  Store,
  RefreshCw,
  Sparkles,
  Wallet,
  Zap,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import "./App.css";

type TransactionRecord = {
  paypal_order_id: string;
  paypal_capture_id: string | null;
  description: string;
  amount: string;
  currency: string;
  status: string;
  created_at: string;
  updated_at: string;
};

type DashboardData = {
  mode: string;
  currency: string;
  balance: string | null;
  money_received: string;
  money_sent: string;
  pending_payments: number;
  transactions: TransactionRecord[];
  notice: string;
};

function formatTransactionDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatMoney(value: string | number, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(Number(value));
}


type MarketplaceProduct = {
  id: string;
  seller_id: string;
  seller_name: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  price: number;
  currency: string;
  image_url: string | null;
  inventory_quantity: number;
};

type MarketplaceResponse = {
  products: MarketplaceProduct[];
  total?: number;
};

type ShoppingChatMessage = { role: "assistant" | "user"; text: string };

function App() {
  const [message, setMessage] = useState("");
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [paymentAmount, setPaymentAmount] = useState("10.00");
  const [paymentDescription, setPaymentDescription] = useState("");
  const [paymentBusy, setPaymentBusy] = useState(false);
const [paymentNotice, setPaymentNotice] = useState("");
const [paymentNoticeType, setPaymentNoticeType] = useState<"success" | "error">("success");
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [dashboardError, setDashboardError] = useState("");
  const [sending, setSending] = useState(false);

  const [activeView, setActiveView] = useState<"overview" | "marketplace">("overview");
  const [products, setProducts] = useState<MarketplaceProduct[]>([]);
  const [productSearch, setProductSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsError, setProductsError] = useState("");
  const [catalogueReload, setCatalogueReload] = useState(0);
  const [shoppingMessage, setShoppingMessage] = useState("");
  const [shoppingSending, setShoppingSending] = useState(false);
  const [shoppingConversation, setShoppingConversation] = useState<ShoppingChatMessage[]>([
    {
      role: "assistant",
      text: "Hi! Tell me what you're looking for, your budget, or the features that matter to you. I'll use the marketplace catalogue to help you compare available listings.",
    },
  ]);


  const categories = Array.from(
    new Set(products.map((product) => product.category).filter(Boolean))
  ).sort();

  const filteredProducts = products.filter((product) => {
    const term = productSearch.trim().toLowerCase();
    const matchesSearch =
      !term ||
      product.name.toLowerCase().includes(term) ||
      product.description.toLowerCase().includes(term) ||
      product.seller_name.toLowerCase().includes(term);
    const matchesCategory =
      selectedCategory === "All" || product.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const [conversation, setConversation] = useState([
    {
      role: "assistant",
      text: "Hi there! I'm your PayPilot AI assistant. I can help you prepare payments, understand transactions, and keep your money moving smoothly.",
    },
  ]);


  useEffect(() => {
    if (activeView !== "marketplace") return;

    let cancelled = false;

    async function loadMarketplace() {
      setProductsLoading(true);
      setProductsError("");

      try {
        const response = await fetch("/api/products?limit=100");
        if (!response.ok) {
          throw new Error("Could not load the product catalogue.");
        }

        const data = (await response.json()) as MarketplaceResponse;
        if (!cancelled) {
          setProducts(Array.isArray(data.products) ? data.products : []);
        }
      } catch (error) {
        if (!cancelled) {
          setProductsError(
            error instanceof Error
              ? error.message
              : "Could not load the product catalogue."
          );
        }
      } finally {
        if (!cancelled) setProductsLoading(false);
      }
    }

    void loadMarketplace();
    return () => {
      cancelled = true;
    };
  }, [activeView, catalogueReload]);

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      try {
        const response = await fetch("http://127.0.0.1:8001/api/dashboard");
        if (!response.ok) throw new Error("Dashboard request failed.");
        const data: DashboardData = await response.json();
        if (!cancelled) {
          setDashboard(data);
          setDashboardError("");
        }
      } catch {
        if (!cancelled) {
          setDashboardError(
            "Can't reach the backend. Make sure the API is running on port 8001."
          );
        }
      }
    }

    void loadDashboard();
    return () => {
      cancelled = true;
    };
  }, []);


  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const paypalState = params.get("paypal");
    const orderId = params.get("token");

    if (paypalState !== "return" && paypalState !== "cancel") return;

    window.history.replaceState({}, document.title, window.location.pathname);

    if (paypalState === "cancel") {
      setPaymentNoticeType("error");
      setPaymentNotice("PayPal checkout was cancelled. No payment was captured.");
      return;
    }

    if (!orderId) {
      setPaymentNoticeType("error");
      setPaymentNotice("PayPal returned without an order ID. Check your Sandbox activity.");
      return;
    }

    let cancelled = false;

    async function captureAndRefresh() {
      setPaymentBusy(true);
      setPaymentNotice("Confirming your PayPal Sandbox payment...");

      try {
        const captureResponse = await fetch(
          `http://127.0.0.1:8001/api/paypal/orders/${encodeURIComponent(orderId!)}/capture`,
          { method: "POST" }
        );
        const captureData = await captureResponse.json();

        if (!captureResponse.ok) {
          throw new Error(captureData.detail || "Could not confirm the PayPal payment.");
        }

        const dashboardResponse = await fetch("http://127.0.0.1:8001/api/dashboard");
        if (!dashboardResponse.ok) {
          throw new Error("Payment was checked, but the dashboard could not refresh.");
        }

        const dashboardData: DashboardData = await dashboardResponse.json();

        if (!cancelled) {
          setDashboard(dashboardData);
          setDashboardError("");
          if (captureData.payment_captured) {
            setPaymentNoticeType("success");
            setPaymentNotice("PayPal Sandbox payment completed and recorded.");
          } else {
            setPaymentNoticeType("error");
            setPaymentNotice(
              `PayPal order status: ${captureData.status || "UNKNOWN"}. The payment is not recorded as completed yet.`
            );
          }
        }
      } catch (error) {
        if (!cancelled) {
          setPaymentNoticeType("error");
          setPaymentNotice(
            error instanceof Error ? error.message : "Unable to confirm the PayPal payment."
          );
        }
      } finally {
        if (!cancelled) setPaymentBusy(false);
      }
    }

    void captureAndRefresh();
    return () => {
      cancelled = true;
    };
  }, []);

  const createPayPalOrder = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const amount = Number(paymentAmount);

    if (!Number.isFinite(amount) || amount <= 0) {
      setPaymentNoticeType("error");
      setPaymentNotice("Enter a valid payment amount greater than zero.");
      return;
    }

    if (!paymentDescription.trim()) {
      setPaymentNoticeType("error");
      setPaymentNotice("Enter a description for this payment.");
      return;
    }

    setPaymentBusy(true);
    setPaymentNotice("");

    try {
      const response = await fetch("http://127.0.0.1:8001/api/paypal/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount: amount.toFixed(2),
          description: paymentDescription.trim(),
        }),
      });

      const data = await response.json();

      if (!response.ok || !data.approval_url) {
        throw new Error(data.detail || "Could not create the PayPal order.");
      }

      window.location.assign(data.approval_url);
    } catch (error) {
      setPaymentNoticeType("error");
      setPaymentNotice(
        error instanceof Error ? error.message : "Could not start the payment."
      );
      setPaymentBusy(false);
    }
  };
  async function sendShoppingMessage() {
    const text = shoppingMessage.trim();
    if (!text || shoppingSending) return;

    setShoppingConversation((items) => [...items, { role: "user", text }]);
    setShoppingMessage("");
    setShoppingSending(true);

    try {
      const response = await fetch("/api/shopping-assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "The shopping assistant is temporarily unavailable."
        );
      }

      setShoppingConversation((items) => [
        ...items,
        {
          role: "assistant",
          text: typeof data.reply === "string"
            ? data.reply
            : "I couldn't prepare a response. Please try again.",
        },
      ]);
    } catch (error) {
      setShoppingConversation((items) => [
        ...items,
        {
          role: "assistant",
          text: error instanceof Error
            ? error.message
            : "I couldn't reach the shopping assistant. Check that the backend is running. No payment was made.",
        },
      ]);
    } finally {
      setShoppingSending(false);
    }
  }

  async function sendMessage() {
    const text = message.trim();
    if (!text || sending) return;

    setConversation((items) => [...items, { role: "user", text }]);
    setMessage("");
    setSending(true);

    try {
      const response = await fetch("http://127.0.0.1:8001/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      if (!response.ok) throw new Error("Assistant request failed.");

      const data: { reply: string } = await response.json();
      setConversation((items) => [
        ...items,
        { role: "assistant", text: data.reply },
      ]);
    } catch {
      setConversation((items) => [
        ...items,
        {
          role: "assistant",
          text: "I couldn't reach the backend. Please check that the API is running on http://127.0.0.1:8001 and try again. No payment was made.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="PayPilot AI home">
          <div className="brand-mark"><Send size={22} strokeWidth={2.5} /></div>
          <span>PayPilot<span className="brand-ai"> AI</span><small>YOUR SMART MONEY COMPANION</small></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="nav-menu">
          <a className="nav-item active" href="#dashboard"><LayoutDashboard size={18} /> Overview</a>
          <a className="nav-item" href="#assistant"><BrainCircuit size={18} /> AI Assistant <span className="nav-badge">AI</span></a>
          <button
            type="button"
            className={`nav-item${activeView === "marketplace" ? " active" : ""}`}
            onClick={() => setActiveView("marketplace")}
          >
            <ShoppingBag size={18} /> Marketplace
          </button>
          <a className="nav-item" href="#transactions"><Activity size={18} /> Transactions</a>
          <a className="nav-item" href="#payments"><Wallet size={18} /> Payments</a>
        </nav>

        <div className="workspace-label tools-label">PREFERENCES</div>
        <nav className="nav-menu">
          <a className="nav-item" href="#settings"><Settings2 size={18} /> Settings</a>
          <a className="nav-item" href="#help"><CircleHelp size={18} /> Help & support</a>
        </nav>

        <div className="sidebar-spacer" />
        <div className="upgrade-card">
          <div className="upgrade-icon"><Sparkles size={17} /></div>
          <strong>Your money, made smarter.</strong>
          <p>Let AI take the busywork out of payments.</p>
          <span className="upgrade-link">Explore PayPilot <ArrowUpRight size={14} /></span>
        </div>
        <div className="profile-row">
          <div className="avatar profile-avatar">G</div>
          <div className="profile-info"><strong>My Workspace</strong><span>Personal account</span></div>
          <ChevronDown size={16} className="muted-icon" />
        </div>
      </aside>

      <main className="main-area" id="dashboard">
        <header className="topbar">
          <div className="breadcrumb">Workspace <span>/</span> <strong>Overview</strong></div>
          <div className="topbar-actions">
            <div className="sandbox-pill"><span /> SANDBOX MODE</div>
            <button className="icon-button" aria-label="Notifications"><Bell size={18} /><i /></button>
            <div className="avatar top-avatar">G</div>
          </div>
        </header>

        <div className="page-content">

  {activeView === "marketplace" && (
    <section className="marketplace-view" id="marketplace">
      <div className="marketplace-hero">
        <div>
          <span className="marketplace-eyebrow">PAYPILOT COMMERCE</span>
          <h1>Discover the marketplace</h1>
          <p>Explore products from independent sellers and growing businesses.</p>
        </div>
        <div className="marketplace-hero-icon"><Store size={28} /></div>
      </div>

      <div className="marketplace-toolbar">
        <label className="marketplace-search">
          <Search size={18} />
          <input
            type="search"
            value={productSearch}
            onChange={(event) => setProductSearch(event.target.value)}
            placeholder="Search products or sellers..."
            aria-label="Search products or sellers"
          />
        </label>

        <select
          className="marketplace-category"
          value={selectedCategory}
          onChange={(event) => setSelectedCategory(event.target.value)}
          aria-label="Filter by category"
        >
          <option value="All">All categories</option>
          {categories.map((category) => (
            <option key={category} value={category}>{category}</option>
          ))}
        </select>

        <button
          type="button"
          className="marketplace-refresh"
          onClick={() => setCatalogueReload((value) => value + 1)}
          disabled={productsLoading}
        >
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {productsError && (
        <div className="marketplace-error" role="alert">
          <p>{productsError}</p>
          <button type="button" onClick={() => setCatalogueReload((value) => value + 1)}>
            Try again
          </button>
        </div>
      )}

      {productsLoading ? (
        <div className="marketplace-message">Loading products...</div>
      ) : productsError ? null : filteredProducts.length === 0 ? (
        <div className="marketplace-empty">
          <div className="marketplace-empty-icon"><ShoppingBag size={30} /></div>
          <h2>{products.length === 0 ? "The marketplace is getting ready" : "No matching products"}</h2>
          <p>
            {products.length === 0
              ? "There are no active products available yet. Products will appear here when sellers are approved and publish their listings."
              : "Try another search term or choose a different category."}
          </p>
          {(productSearch || selectedCategory !== "All") && (
            <button
              type="button"
              className="marketplace-refresh"
              onClick={() => {
                setProductSearch("");
                setSelectedCategory("All");
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      ) : (
        <>
          <p className="marketplace-results-count">
            {filteredProducts.length} {filteredProducts.length === 1 ? "product" : "products"}
          </p>
          <div className="marketplace-product-grid">
            {filteredProducts.map((product) => (
              <article className="marketplace-product-card" key={product.id}>
                {product.image_url ? (
                  <img
                    className="marketplace-product-image"
                    src={product.image_url}
                    alt={product.name}
                    onError={(event) => {
                      event.currentTarget.style.display = "none";
                    }}
                  />
                ) : (
                  <div className="marketplace-product-placeholder">
                    <ShoppingBag size={34} />
                  </div>
                )}
                <div className="marketplace-product-body">
                  <span className="marketplace-category-tag">
                    {product.category || "General"}
                  </span>
                  <h2>{product.name}</h2>
                  <p className="marketplace-product-description">
                    {product.description || "No description provided."}
                  </p>
                  <p className="marketplace-seller">Sold by {product.seller_name}</p>
                  <div className="marketplace-product-bottom">
                    <strong>{formatMoney(product.price, product.currency)}</strong>
                    <span>{product.inventory_quantity} available</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      <section className="marketplace-assistant" aria-labelledby="shopping-assistant-title">
        <div className="marketplace-assistant-heading">
          <div className="marketplace-assistant-icon"><Bot size={21} /></div>
          <div>
            <h2 id="shopping-assistant-title">Your AI shopping assistant</h2>
            <p>Describe what you need. Recommendations are based on current marketplace listings.</p>
          </div>
        </div>

        <div className="marketplace-chat" aria-live="polite" aria-label="Shopping conversation">
          {shoppingConversation.map((item, index) => (
            <div
              className={`marketplace-chat-row ${item.role === "user" ? "user" : "assistant"}`}
              key={`${index}-${item.role}`}
            >
              {item.role === "assistant" && (
                <span className="marketplace-chat-avatar"><Bot size={15} /></span>
              )}
              <p className="marketplace-chat-bubble">{item.text}</p>
            </div>
          ))}
          {shoppingSending && (
            <div className="marketplace-chat-status">Checking available listings...</div>
          )}
        </div>

        <form
          className="marketplace-chat-form"
          onSubmit={(event: FormEvent<HTMLFormElement>) => {
            event.preventDefault();
            void sendShoppingMessage();
          }}
        >
          <input
            type="text"
            value={shoppingMessage}
            onChange={(event) => setShoppingMessage(event.target.value)}
            placeholder="e.g. I need a useful gift under $30"
            aria-label="Ask the shopping assistant"
            maxLength={1000}
            disabled={shoppingSending}
          />
          <button type="submit" disabled={shoppingSending || !shoppingMessage.trim()}>
            <Send size={16} />
            <span>{shoppingSending ? "Thinking..." : "Ask"}</span>
          </button>
        </form>

        <p className="marketplace-chat-disclaimer">
          <ShieldCheck size={14} />
          Advice only. Product purchases and marketplace checkout are not enabled yet.
          The assistant cannot create or capture payments.
        </p>
      </section>

      <p className="marketplace-product-note">
        Product ordering, marketplace checkout and multi-seller payouts are not enabled yet.
      </p>
    </section>
  )}

  <div hidden={activeView !== "overview"}>
  {paymentOpen && (
            <section className="panel payment-form-panel" id="new-payment">
              <div className="panel-heading">
                <div>
                  <h2>New PayPal payment</h2>
                  <p>Create a Sandbox order and approve it securely on PayPal.</p>
                </div>
                <button type="button" className="text-button" onClick={() => setPaymentOpen(false)}>
                  Cancel
                </button>
              </div>

              <form onSubmit={createPayPalOrder} className="payment-form">
                <label htmlFor="payment-amount">Amount (USD)</label>
                <input
                  id="payment-amount"
                  type="number"
                  min="0.01"
                  max="10000"
                  step="0.01"
                  required
                  value={paymentAmount}
                  onChange={(event) => setPaymentAmount(event.target.value)}
                  disabled={paymentBusy}
                />

                <label htmlFor="payment-description">Payment description</label>
                <input
                  id="payment-description"
                  type="text"
                  maxLength={127}
                  required
                  value={paymentDescription}
                  onChange={(event) => setPaymentDescription(event.target.value)}
                  placeholder="e.g. Design services"
                  disabled={paymentBusy}
                />

                {paymentNotice && (
                  <p role="status" className={paymentNoticeType === "error" ? "payment-notice error" : "payment-notice success"}>
                    {paymentNotice}
                  </p>
                )}

                <div className="payment-form-actions">
                  <button type="submit" className="primary-button" disabled={paymentBusy}>
                    <CreditCard size={17} />
                    {paymentBusy ? "Connecting to PayPal..." : "Continue to PayPal"}
                  </button>
                  <span className="payment-sandbox-note">
                    Sandbox testing only. Review the order before approving it.
                  </span>
                </div>
              </form>
            </section>
          )}
          <section className="welcome-row">
            <div>
              <div className="eyebrow"><Sparkles size={14} /> YOUR FINANCIAL COPILOT</div>
              <h1>Good morning<span className="wave"> ✨</span></h1>
              <p className="page-subtitle">Your money moves. Let's make every move count.</p>
            </div>
            <button className="primary-button" onClick={() => { setPaymentNotice(""); setPaymentOpen(true); }}><Plus size={18} /> New payment</button>
          </section>

          <section className="stat-grid">
            {dashboardError && <p role="alert" className="stat-note">{dashboardError}</p>}
            <article className="stat-card balance-card">
              <div className="stat-top"><span>Sandbox balance</span><div className="stat-icon purple"><Wallet size={19} /></div></div>
              <div className="stat-value">{dashboard ? (dashboard.balance === null ? "Unavailable" : formatMoney(dashboard.balance, dashboard.currency)) : "Loading..."}</div>
              <div className="stat-foot"><span className="status-dot" /> PayPal balance <span className="stat-note">Unavailable via this API</span></div>
            </article>
            <article className="stat-card">
              <div className="stat-top"><span>Money received</span><div className="stat-icon green"><ArrowDownLeft size={19} /></div></div>
              <div className="stat-value">{dashboard ? formatMoney(dashboard.money_received, dashboard.currency) : "Loading..."}</div>
              <div className="stat-foot"><span className="trend-positive"><ArrowDownLeft size={13} /> Incoming payments</span><span className="stat-note">Not yet supported</span></div>
            </article>
            <article className="stat-card">
              <div className="stat-top"><span>Money sent</span><div className="stat-icon blue"><ArrowUpRight size={19} /></div></div>
              <div className="stat-value">{dashboard ? formatMoney(dashboard.money_sent, dashboard.currency) : "Loading..."}</div>
              <div className="stat-foot"><span className="trend-neutral"><Activity size={13} /> Completed orders</span><span className="stat-note">All recorded time</span></div>
            </article>
            <article className="stat-card">
              <div className="stat-top"><span>Pending payments</span><div className="stat-icon amber"><Clock3 size={19} /></div></div>
              <div className="stat-value">{dashboard ? String(dashboard.pending_payments).padStart(2, "0") : "—"}</div>
              <div className="stat-foot"><span className="pending-text">Awaiting capture</span><span className="stat-note">Recorded orders</span></div>
            </article>
          </section>

          <section className="content-grid">
            <article className="panel assistant-panel" id="assistant">
              <div className="panel-heading">
                <div className="assistant-title">
                  <div className="assistant-icon"><Bot size={21} /></div>
                  <div><h2>Your AI assistant</h2><p>Your goals, translated into action.</p></div>
                </div>
                <span className="online-pill"><span /> READY</span>
              </div>

              <div className="assistant-banner">
                <div className="banner-spark"><Sparkles size={19} /></div>
                <div><strong>What can I help you with?</strong><p>Tell me what you need to do. We'll figure out the next step together.</p></div>
              </div>

              <div className="conversation">
                {conversation.map((item, index) => (
                  <div className={`message-row ${item.role}`} key={index}>
                    {item.role === "assistant" && <div className="message-avatar"><Bot size={15} /></div>}
                    <div className="message-bubble">{item.text}</div>
                  </div>
                ))}
              </div>

              {sending && <p role="status">PayPilot is preparing a response...</p>}
              <div className="suggestion-label">TRY ASKING</div>
              <div className="suggestion-list">
                <button onClick={() => setMessage("Help me prepare a payment for a contractor")}> <CreditCard size={15} /> Prepare a payment <ArrowUpRight size={13} /></button>
                <button onClick={() => setMessage("Explain my recent transactions")}> <Activity size={15} /> Explain my transactions <ArrowUpRight size={13} /></button>
              </div>

              <form className="chat-input-wrap" onSubmit={(event) => { event.preventDefault(); sendMessage(); }}>
                <input id="assistant-input" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask anything about your payments..." aria-label="Message the AI assistant" />
                <button type="submit" aria-label="Send message" disabled={!message.trim() || sending}><Send size={17} /></button>
              </form>
              <div className="privacy-note"><ShieldCheck size={13} /> Your payments always stay in your control.</div>
            </article>

            <div className="right-column">
              <article className="panel quick-panel" id="payments">
                <div className="panel-heading"><div><h2>Quick actions</h2><p>Good things happen in a few clicks.</p></div></div>
                <div className="quick-actions">
                  <button onClick={() => { setPaymentNotice(""); setPaymentOpen(true); }}><div className="quick-icon lavender"><Send size={19} /></div><span><strong>Send money</strong><small>Prepare a payment</small></span><ArrowUpRight size={16} className="quick-arrow" /></button>
                  <button onClick={() => { setMessage("Help me understand money I can receive"); document.getElementById("assistant-input")?.focus(); }}><div className="quick-icon mint"><ArrowDownLeft size={19} /></div><span><strong>Request money</strong><small>Explore payment requests</small></span><ArrowUpRight size={16} className="quick-arrow" /></button>
                  <button onClick={() => { setMessage("Give me a summary of my payment activity"); document.getElementById("assistant-input")?.focus(); }}><div className="quick-icon peach"><Activity size={19} /></div><span><strong>Payment insights</strong><small>Understand your activity</small></span><ArrowUpRight size={16} className="quick-arrow" /></button>
                </div>
              </article>

              <article className="panel transactions-panel" id="transactions">
                <div className="panel-heading transaction-heading"><div><h2>Recent activity</h2><p>Your money at a glance.</p></div><button className="text-button" onClick={() => document.getElementById("transactions-list")?.scrollIntoView({ behavior: "smooth", block: "center" })}>View all <ArrowUpRight size={14} /></button></div>
                <div className="transaction-list" id="transactions-list">
                  {!dashboard ? (
                    <p className="stat-note">Loading recorded transactions...</p>
                  ) : dashboard.transactions.length === 0 ? (
                    <p className="stat-note">No transactions yet. Create a Sandbox payment to see it here.</p>
                  ) : (
                    dashboard.transactions.map((tx) => {
                      const completed = tx.status === "COMPLETED";
                      return (
                        <div className="transaction-row" key={tx.paypal_order_id}>
                          <div className="transaction-avatar out"><ArrowUpRight size={17} /></div>
                          <div className="transaction-info">
                            <strong>{tx.description}</strong>
                            <span>Order {tx.paypal_order_id} ? {formatTransactionDate(tx.created_at)}</span>
                            <span className={`transaction-status ${completed ? "" : "pending"}`}>
                              {completed ? <CheckCircle2 size={11} /> : <Clock3 size={11} />} {tx.status}
                            </span>
                          </div>
                          <strong className="transaction-amount out">-{formatMoney(tx.amount, tx.currency)}</strong>
                        </div>
                      );
                    })
                  )}
                </div>
                <div className="demo-disclaimer"><ShieldCheck size={14} /> Recorded transactions from this PayPilot AI instance. Sandbox activity is test activity, not real money.</div>
              </article>
            </div>
          </section>

          <footer className="page-footer"><span>© 2026 PayPilot AI</span><span><ShieldCheck size={13} /> Built with security in mind</span><span><Zap size={13} /> Powered by intelligent workflows</span></footer>
        </div>
        </div>
      </main>
    </div>
  );
}

export default App;
