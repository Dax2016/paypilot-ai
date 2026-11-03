import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Bell,
  Bot,
  BrainCircuit,
  BookOpen,
  Flame,
  Award,
  CheckCircle2,
  Clock3,
  CreditCard,
  LayoutDashboard,
  Plus,
  Send,
  ShieldCheck,
  Search,
  ShoppingBag,
  ShoppingCart,
  Minus,
  Trash2,
  Store,
  RefreshCw,
  Sparkles,
  Wallet,
  Zap,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { apiUrl } from "./api";
import "./App.css";

type CustomerAccount = {
  id: string;
  email: string;
  created_at?: string;
};

type AuthResponse = {
  access_token: string;
  token_type: string;
  expires_at: string;
  account: CustomerAccount;
};

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

type SemanticResponse = {
  intent?: string;
  answer?: string;
  key_points?: string[];
  evidence?: Array<Record<string, unknown>>;
  recommendations?: string[];
  next_action?: string | null;
};

type ChatMessage = {
  role: "assistant" | "user";
  text: string;
  semantic?: SemanticResponse;
};

type PayPalOfficialLinks = {
  account?: string;
  business?: string;
  sign_in?: string;
};

type ShoppingChatMessage = ChatMessage & {
  recommendedProductIds?: string[];
  paypalOfficialLinks?: PayPalOfficialLinks;
  paypalCountryCode?: string;
};

function SemanticDetails({ semantic }: { semantic?: SemanticResponse }) {
  if (!semantic) return null;

  const displayValue = (value: unknown): string => {
    if (Array.isArray(value)) return `${value.length} items`;
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return "Details available";
    if (typeof value === "boolean") return value ? "Yes" : "No";
    return String(value);
  };

  const labelFor = (value: string) =>
    value.replace(/_/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());

  const rows = (semantic.evidence ?? []).flatMap((record, index) =>
    Object.entries(record)
      .filter(([key]) => key.toLowerCase() !== "product_ids")
      .filter(([, value]) =>
        value === null ||
        ["string", "number", "boolean"].includes(typeof value) ||
        Array.isArray(value)
      )
      .map(([key, value]) => ({
        id: `${index}-${key}`,
        label: labelFor(key),
        value: displayValue(value),
      }))
  );

  if (
    !semantic.key_points?.length &&
    !rows.length &&
    !semantic.recommendations?.length &&
    !semantic.next_action
  ) return null;

  return (
    <div className="semantic-details">
      {!!semantic.key_points?.length && (
        <section className="semantic-section">
          <h4>Key points</h4>
          <ul>{semantic.key_points.map((point, i) =>
            <li key={`${i}-${point}`}>{point}</li>
          )}</ul>
        </section>
      )}
      {!!rows.length && (
        <section className="semantic-section">
          <h4>Supporting evidence</h4>
          <dl className="semantic-evidence">
            {rows.map(row => (
              <div key={row.id}>
                <dt>{row.label}</dt><dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {!!semantic.recommendations?.length && (
        <section className="semantic-section">
          <h4>Recommendations</h4>
          <ul>{semantic.recommendations.map((item, i) =>
            <li key={`${i}-${item}`}>{item}</li>
          )}</ul>
        </section>
      )}
      {semantic.next_action && (
        <p className="semantic-next-action">
          <strong>Suggested next step:</strong> {semantic.next_action}
        </p>
      )}
    </div>
  );
}

type CartItem = {
  product: MarketplaceProduct;
  quantity: number;
};

type MarketplaceOrderItem = {
  product_id: string;
  product_name: string;
  unit_price_minor: number;
  quantity: number;
  line_total_minor: number;
};

type MarketplaceOrder = {
  id: string;
  paypal_order_id: string;
  paypal_capture_id: string | null;
  amount_minor: number;
  currency: string;
  status: string;
  created_at: string;
  updated_at: string;
  items: MarketplaceOrderItem[];
};

type AdminDraftProduct = {
  id: string;
  seller_id: string;
  seller_name: string;
  seller_email: string;
  seller_status: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  price: string;
  currency: string;
  image_url: string | null;
  inventory_quantity: number;
  status: string;
  created_at?: string;
};

type SellerProfile = {
  id: string;
  display_name: string;
  email: string;
  status: string;
  created_at?: string;
  updated_at?: string;
};

type SellerProduct = {
  id: string;
  seller_id: string;
  name: string;
  description: string;
  category: string;
  price_minor: number;
  price: string;
  currency: string;
  image_url: string | null;
  inventory_quantity: number;
  status: string;
  created_at?: string;
  updated_at?: string;
};
type ActiveView =
  | "overview"
  | "marketplace"
  | "orders"
  | "admin"
  | "seller"
  | "paypal-iq";


type PayPalIQFact = {
  id: string;
  fact_code?: string;
  title: string;
  fact_text: string;
  explanation?: string | null;
  category: string;
  country_scope?: string;
  country_code?: string | null;
  source_url?: string | null;
  source_title?: string | null;
  source_type?: string | null;
  source_excerpt?: string | null;
  verified_at?: string | null;
  review_at?: string | null;
  fact_version?: number;
  difficulty?: string;
};

type PayPalIQQuestion = {
  id: string;
  fact_id: string;
  question: string;
  options: string[];
  difficulty: string;
  fact_title: string;
  category: string;
};

type PayPalIQProgress = {
  total_points: number;
  quizzes_completed: number;
  facts_viewed: number;
  current_streak: number;
  longest_streak: number;
  last_activity_date: string | null;
};

type PayPalIQQuizResult = {
  question_id: string;
  selected_option: string;
  is_correct: boolean;
  correct_option: string;
  explanation: string;
  points_awarded: number;
  questions_answered_today: number;
  quiz_completed_today: boolean;
};
type OverviewSection =
  | "dashboard"
  | "assistant"
  | "transactions"
  | "payments";

type SellerApplication = {
  id: string;
  display_name: string;
  email: string;
  status: string;
  created_at?: string;
  updated_at?: string;
};

type AdminSellersResponse = {
  sellers: SellerApplication[];
  total: number;
  status: string;
};

type AdminDraftsResponse = {
  products: AdminDraftProduct[];
  total: number;
  status: string;
};

type MarketplaceOrdersResponse = {
  orders: MarketplaceOrder[];
  count: number;
};

function App() {
  // Customer tokens live in React memory only; refreshing the page signs out.
  const [authToken, setAuthToken] = useState("");
  const [authAccount, setAuthAccount] = useState<CustomerAccount | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
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

  const [activeView, setActiveView] = useState<ActiveView>("overview");
  const [paypalIQDailyFact, setPaypalIQDailyFact] = useState<PayPalIQFact | null>(null);
  const [paypalIQFacts, setPaypalIQFacts] = useState<PayPalIQFact[]>([]);
  const [paypalIQCategories, setPaypalIQCategories] = useState<string[]>([]);
  const [paypalIQQuestions, setPaypalIQQuestions] = useState<PayPalIQQuestion[]>([]);
  const [paypalIQProgress, setPaypalIQProgress] = useState<PayPalIQProgress | null>(null);
  const [paypalIQResults, setPaypalIQResults] = useState<Record<string, PayPalIQQuizResult>>({});
  const [paypalIQSelectedAnswers, setPaypalIQSelectedAnswers] = useState<Record<string, string>>({});
  const [paypalIQSelectedCategory, setPaypalIQSelectedCategory] = useState("ALL");
  const [paypalIQLoading, setPaypalIQLoading] = useState(false);
  const [paypalIQError, setPaypalIQError] = useState("");
  const [activeSection, setActiveSection] =
    useState<OverviewSection>("dashboard");
  const [pendingSection, setPendingSection] =
    useState<OverviewSection | null>(null);
  const [products, setProducts] = useState<MarketplaceProduct[]>([]);
  const [cartItems, setCartItems] = useState<CartItem[]>([]);
  const [productSearch, setProductSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsError, setProductsError] = useState("");
  const [catalogueReload, setCatalogueReload] = useState(0);
  const [draftSellerId, setDraftSellerId] = useState("2f9415cc-281d-4fab-8d3d-6dcae6d7c523");
  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftCategory, setDraftCategory] = useState("General");
  const [draftPrice, setDraftPrice] = useState("");
  const [draftStock, setDraftStock] = useState("1");
  const [draftImageUrl, setDraftImageUrl] = useState("");
  const [draftSubmitting, setDraftSubmitting] = useState(false);
  const [draftNotice, setDraftNotice] = useState("");
  const [draftNoticeType, setDraftNoticeType] = useState<"success" | "error">("success");

  // Local demo admin access. Never persist this token in localStorage.
  const [adminToken, setAdminToken] = useState("");
  const [adminDrafts, setAdminDrafts] = useState<AdminDraftProduct[]>([]);
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminError, setAdminError] = useState("");
  const [adminNotice, setAdminNotice] = useState("");
  const [adminBusyProductId, setAdminBusyProductId] = useState("");
  const [adminSellers, setAdminSellers] = useState<SellerApplication[]>([]);
  const [adminSellersLoading, setAdminSellersLoading] = useState(false);
  const [adminBusySellerId, setAdminBusySellerId] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [sellerEmail, setSellerEmail] = useState("");
  const [sellerRegistering, setSellerRegistering] = useState(false);
  const [sellerLookupId, setSellerLookupId] = useState("2f9415cc-281d-4fab-8d3d-6dcae6d7c523");
  const [sellerProfile, setSellerProfile] = useState<SellerProfile | null>(null);
  const [sellerProducts, setSellerProducts] = useState<SellerProduct[]>([]);
  const [sellerLoading, setSellerLoading] = useState(false);
  const [sellerError, setSellerError] = useState("");
  const [sellerNotice, setSellerNotice] = useState("");


  const [orders, setOrders] = useState<MarketplaceOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState("");
  const [ordersReload, setOrdersReload] = useState(0);
  const [shoppingMessage, setShoppingMessage] = useState("");
  const [shoppingSending, setShoppingSending] = useState(false);
  const [marketplaceCheckoutBusy, setMarketplaceCheckoutBusy] = useState(false);
  const [marketplaceNotice, setMarketplaceNotice] = useState("");
  const [marketplaceNoticeType, setMarketplaceNoticeType] =
    useState<"success" | "error" | "info">("info");
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

  const cartCount = cartItems.reduce((sum, item) => sum + item.quantity, 0);
  const cartTotalMinor = cartItems.reduce(
    (sum, item) => sum + item.product.price_minor * item.quantity,
    0
  );

  async function handleMarketplaceCheckout() {
    if (cartItems.length === 0 || marketplaceCheckoutBusy) return;

    setMarketplaceCheckoutBusy(true);
    setMarketplaceNotice("");
    setMarketplaceNoticeType("info");

    try {
      const response = await fetch(apiUrl("/api/marketplace/orders"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: cartItems.map(({ product, quantity }) => ({
            product_id: product.id,
            quantity,
          })),
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to start marketplace checkout."
        );
      }

      if (!data.approval_url || !data.order_id) {
        throw new Error("The server did not return a PayPal approval link.");
      }

      window.location.assign(data.approval_url);
    } catch (error) {
      setMarketplaceNotice(
        error instanceof Error ? error.message : "Marketplace checkout failed."
      );
      setMarketplaceNoticeType("error");
      setMarketplaceCheckoutBusy(false);
    }
  }

  function addToCart(product: MarketplaceProduct) {
    setCartItems((current) => {
      const existing = current.find((item) => item.product.id === product.id);
      if (existing) {
        if (existing.quantity >= product.inventory_quantity) return current;
        return current.map((item) =>
          item.product.id === product.id
            ? { ...item, product, quantity: item.quantity + 1 }
            : item
        );
      }
      if (product.inventory_quantity < 1) return current;
      return [...current, { product, quantity: 1 }];
    });
  }

  function changeCartQuantity(productId: string, delta: number) {
    setCartItems((current) =>
      current
        .map((item) => {
          if (item.product.id !== productId) return item;
          const quantity = Math.min(
            item.product.inventory_quantity,
            item.quantity + delta
          );
          return { ...item, quantity };
        })
        .filter((item) => item.quantity > 0)
    );
  }

  function removeFromCart(productId: string) {
    setCartItems((current) =>
      current.filter((item) => item.product.id !== productId)
    );
  }


  async function submitProductDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setDraftSubmitting(true);
    setDraftNotice("");

    try {
      const response = await fetch(
        apiUrl(`/api/sellers/${encodeURIComponent(draftSellerId.trim())}/products`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: draftName.trim(),
            description: draftDescription.trim(),
            category: draftCategory.trim(),
            price: draftPrice,
            currency: "USD",
            inventory_quantity: Number(draftStock),
            image_url: draftImageUrl.trim() || null,
          }),
        }
      );

      const data = await response.json();
      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Product submission failed."
        );
      }

      setDraftNotice(
        `Draft saved: ${data.name}. An administrator must publish it before it appears in the marketplace.`
      );
      setDraftNoticeType("success");
      setDraftName("");
      setDraftDescription("");
      setDraftCategory("General");
      setDraftPrice("");
      setDraftStock("1");
      setDraftImageUrl("");
      if (sellerProfile?.id === draftSellerId.trim()) {
        await loadSellerDashboard(sellerProfile.id);
      }
    } catch (error) {
      setDraftNotice(
        error instanceof Error ? error.message : "Product submission failed."
      );
      setDraftNoticeType("error");
    } finally {
      setDraftSubmitting(false);
    }
  }

  async function loadAdminSellers() {
    if (!adminToken.trim()) {
      setAdminError("Enter the admin token to load seller applications.");
      return;
    }

    setAdminSellersLoading(true);
    setAdminError("");

    try {
      const response = await fetch(apiUrl("/api/admin/sellers?status=PENDING&limit=100"), {
        headers: { "X-Admin-Token": adminToken.trim() },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || "Could not load seller applications.");
      }

      const result = data as AdminSellersResponse;
      setAdminSellers(Array.isArray(result.sellers) ? result.sellers : []);
    } catch (error) {
      setAdminError(
        error instanceof Error ? error.message : "Could not load seller applications."
      );
    } finally {
      setAdminSellersLoading(false);
    }
  }

  async function approveSellerApplication(seller: SellerApplication) {
    if (!adminToken.trim()) {
      setAdminError("Enter the admin token before approving a seller.");
      return;
    }

    const confirmed = window.confirm(
      `Approve "${seller.display_name}"? This will activate the seller account.`
    );
    if (!confirmed) return;

    setAdminBusySellerId(seller.id);
    setAdminError("");
    setAdminNotice("");

    try {
      const response = await fetch(apiUrl(`/api/admin/sellers/${encodeURIComponent(seller.id)}/approve`),
        {
          method: "POST",
          headers: { "X-Admin-Token": adminToken.trim() },
        }
      );
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || "Could not approve this seller.");
      }

      await loadAdminSellers();
      await loadAdminDrafts();
      setAdminNotice(`"${seller.display_name}" has been approved. They can now submit product listings.`);
    } catch (error) {
      setAdminError(
        error instanceof Error ? error.message : "Could not approve this seller."
      );
    } finally {
      setAdminBusySellerId("");
    }
  }

  async function loadAdminDrafts() {
    if (!adminToken.trim()) {
      setAdminError("Enter the admin token to load product submissions.");
      return;
    }

    setAdminLoading(true);
    setAdminError("");
    setAdminNotice("");

    try {
      const response = await fetch(apiUrl("/api/admin/products?status=DRAFT&limit=100"), {
        headers: { "X-Admin-Token": adminToken.trim() },
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Could not load product submissions."
        );
      }

      const result = data as AdminDraftsResponse;
      setAdminDrafts(Array.isArray(result.products) ? result.products : []);
    } catch (error) {
      setAdminError(
        error instanceof Error ? error.message : "Could not load product submissions."
      );
    } finally {
      setAdminLoading(false);
    }
  }

  async function reviewProduct(product: AdminDraftProduct, action: "publish" | "reject") {
    if (!adminToken.trim() || adminBusyProductId) return;

    const confirmed = window.confirm(
      action === "publish"
        ? `Publish "${product.name}" to the public marketplace?`
        : `Reject and archive "${product.name}"?`
    );
    if (!confirmed) return;

    setAdminBusyProductId(product.id);
    setAdminError("");
    setAdminNotice("");

    try {
      const response = await fetch(apiUrl(`/api/admin/products/${encodeURIComponent(product.id)}/${action}`),
        {
          method: "POST",
          headers: { "X-Admin-Token": adminToken.trim() },
        }
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : `Could not ${action} this product.`
        );
      }

      setAdminNotice(
        action === "publish"
          ? `"${product.name}" is now published.`
          : `"${product.name}" was rejected and archived.`
      );

      await loadAdminDrafts();
      setCatalogueReload((value) => value + 1);
    } catch (error) {
      setAdminError(
        error instanceof Error ? error.message : `Could not ${action} this product.`
      );
    } finally {
      setAdminBusyProductId("");
    }
  }

  const [conversation, setConversation] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Hi there! I'm your PayPilot AI assistant. I can help you prepare payments, understand transactions, and keep your money moving smoothly.",
    },
  ]);


  const navigateToView = (view: ActiveView) => {
    setActiveView(view);
    setActiveSection("dashboard");
    setPendingSection(null);
  };

  const navigateToSection = (section: OverviewSection) => {
    setActiveView("overview");
    setActiveSection(section);
    setPendingSection(section);
  };

  useEffect(() => {
    if (activeView !== "overview" || pendingSection === null) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      document.getElementById(pendingSection)?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });

      setPendingSection(null);
    });

    return () => window.cancelAnimationFrame(frame);
  }, [activeView, pendingSection]);
  useEffect(() => {
    if (activeView !== "paypal-iq" || !authToken) return;

    let cancelled = false;

    async function loadPayPalIQ() {
      setPaypalIQLoading(true);
      setPaypalIQError("");

      const headers = {
        Authorization: `Bearer ${authToken}`,
      };

      try {
        const [dailyResponse, factsResponse, categoriesResponse, quizResponse, progressResponse] =
          await Promise.all([
            fetch(apiUrl("/api/paypal-iq/daily"), { headers }),
            fetch(apiUrl("/api/paypal-iq/facts"), { headers }),
            fetch(apiUrl("/api/paypal-iq/categories"), { headers }),
            fetch(apiUrl("/api/paypal-iq/quiz"), { headers }),
            fetch(apiUrl("/api/paypal-iq/progress"), { headers }),
          ]);

        const responses = [
          dailyResponse,
          factsResponse,
          categoriesResponse,
          quizResponse,
          progressResponse,
        ];

        if (responses.some((response) => !response.ok)) {
          throw new Error("Could not load PayPal IQ. Please try again.");
        }

        const [dailyData, factsData, categoriesData, quizData, progressData] =
          await Promise.all([
            dailyResponse.json(),
            factsResponse.json(),
            categoriesResponse.json(),
            quizResponse.json(),
            progressResponse.json(),
          ]);

        if (cancelled) return;

        setPaypalIQDailyFact(dailyData.fact ?? null);
        setPaypalIQFacts(Array.isArray(factsData.items) ? factsData.items : []);
        setPaypalIQCategories(
          Array.isArray(categoriesData.categories) ? categoriesData.categories : []
        );
        setPaypalIQQuestions(
          Array.isArray(quizData.questions) ? quizData.questions : []
        );
        setPaypalIQProgress(progressData.progress ?? null);
        setPaypalIQResults({});
        setPaypalIQSelectedAnswers({});
      } catch (error) {
        if (!cancelled) {
          setPaypalIQError(
            error instanceof Error
              ? error.message
              : "Could not load PayPal IQ."
          );
        }
      } finally {
        if (!cancelled) setPaypalIQLoading(false);
      }
    }

    void loadPayPalIQ();

    return () => {
      cancelled = true;
    };
  }, [activeView, authToken]);
  useEffect(() => {
    if (activeView !== "marketplace") return;

    let cancelled = false;

    async function loadMarketplace() {
      setProductsLoading(true);
      setProductsError("");

      try {
        const response = await fetch(apiUrl("/api/products?limit=100"));
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
    if (activeView !== "orders") return;

    if (!adminToken.trim()) {
      setOrders([]);
      setOrdersError("Enter your admin token in Admin Review to access order history.");
      return;
    }

    let cancelled = false;

    async function loadOrders() {
      setOrdersLoading(true);
      setOrdersError("");

      try {
        const response = await fetch(apiUrl("/api/marketplace/orders?limit=50"), {
          headers: { "X-Admin-Token": adminToken.trim() },
        });
        if (!response.ok) {
          throw new Error("Could not load marketplace orders.");
        }

        const data = (await response.json()) as MarketplaceOrdersResponse;
        if (!cancelled) {
          setOrders(Array.isArray(data.orders) ? data.orders : []);
        }
      } catch (error) {
        if (!cancelled) {
          setOrdersError(
            error instanceof Error
              ? error.message
              : "Could not load marketplace orders."
          );
        }
      } finally {
        if (!cancelled) setOrdersLoading(false);
      }
    }

    void loadOrders();
    return () => {
      cancelled = true;
    };
  }, [activeView, ordersReload, adminToken]);

  useEffect(() => {
    let cancelled = false;

    async function loadDashboard() {
      try {
        const response = await fetch(apiUrl("/api/dashboard"));
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
    const marketplaceState = params.get("marketplace_paypal");
    const orderId = params.get("token");

    if (marketplaceState !== "return" && marketplaceState !== "cancel") return;

    window.history.replaceState({}, document.title, window.location.pathname);

    if (marketplaceState === "cancel") {
      const localOrderId = params.get("local_order_id");

      if (!localOrderId) {
        setMarketplaceNotice(
          "Checkout was closed. Your cart is unchanged."
        );
        setMarketplaceNoticeType("error");
        return;
      }

      let cancellationEffectCancelled = false;

      async function recordMarketplaceCancellation() {
        try {
          const response = await fetch(
            apiUrl(
              `/api/marketplace/orders/${encodeURIComponent(localOrderId as string)}/cancel`
            ),
            { method: "POST" }
          );

          const data = await response.json();

          if (!response.ok) {
            throw new Error(
              typeof data.detail === "string"
                ? data.detail
                : "Could not verify the marketplace order."
            );
          }

          if (cancellationEffectCancelled) return;

          setMarketplaceNotice(
            data.message ||
              "Checkout was closed. The order may still be pending."
          );
          setMarketplaceNoticeType(data.cancelled ? "error" : "info");
        } catch (error) {
          if (cancellationEffectCancelled) return;

          setMarketplaceNotice(
            error instanceof Error
              ? error.message
              : "Could not verify the marketplace order. Your cart is unchanged."
          );
          setMarketplaceNoticeType("error");
        }
      }

      void recordMarketplaceCancellation();

      return () => {
        cancellationEffectCancelled = true;
      };
    }

    if (!orderId) {
      setMarketplaceNotice("PayPal returned without an order ID. Your cart is unchanged.");
      setMarketplaceNoticeType("error");
      return;
    }

    let cancelled = false;

    async function captureMarketplaceOrder() {
      setMarketplaceCheckoutBusy(true);
      setMarketplaceNotice("Confirming your marketplace payment with PayPal Sandbox...");
      setMarketplaceNoticeType("info");

      try {
        const response = await fetch(
          apiUrl(`/api/marketplace/orders/${encodeURIComponent(orderId!)}/capture`),
          { method: "POST" }
        );
        const data = await response.json();

        if (!response.ok) {
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "Could not confirm your marketplace payment."
          );
        }

        if (!data.payment_captured) {
          throw new Error(data.message || "PayPal has not confirmed the payment.");
        }

        if (cancelled) return;

        setCartItems([]);
        setCatalogueReload((current) => current + 1);
        setMarketplaceNotice("Payment successful! Your marketplace order is confirmed.");
        setMarketplaceNoticeType("success");
      } catch (error) {
        if (cancelled) return;
        setMarketplaceNotice(
          error instanceof Error ? error.message : "Payment confirmation failed."
        );
        setMarketplaceNoticeType("error");
      } finally {
        if (!cancelled) setMarketplaceCheckoutBusy(false);
      }
    }

    void captureMarketplaceOrder();

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
          apiUrl(`/api/paypal/orders/${encodeURIComponent(orderId!)}/capture`),
          { method: "POST" }
        );
        const captureData = await captureResponse.json();

        if (!captureResponse.ok) {
          throw new Error(captureData.detail || "Could not confirm the PayPal payment.");
        }

        const dashboardResponse = await fetch(apiUrl("/api/dashboard"));
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
      const response = await fetch(apiUrl("/api/paypal/orders"), {
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
  async function openPayPalResource(
    resourceKey: "account" | "business" | "sign_in",
    url: string,
    countryCode: string
  ) {
    // Open immediately from the click gesture; analytics must never block navigation.
    const paypalWindow = window.open(url, "_blank", "noopener,noreferrer");

    try {
      await fetch(apiUrl("/api/paypal/promo-clicks"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resource_key: resourceKey,
          country_code: countryCode,
        }),
      });
    } catch {
      // A tracking failure must not prevent access to the official PayPal page.
    }

    if (!paypalWindow) {
      window.location.assign(url);
    }
  }

  async function sendShoppingMessage() {
    const text = shoppingMessage.trim();
    if (!text || shoppingSending) return;

    setShoppingConversation((items) => [...items, { role: "user", text }]);
    setShoppingMessage("");
    setShoppingSending(true);

    try {
      const response = await fetch(apiUrl("/api/shopping-assistant"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
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
          semantic:
            data.semantic_response && typeof data.semantic_response === "object"
              ? data.semantic_response as SemanticResponse
              : undefined,
          recommendedProductIds: Array.isArray(data.recommended_product_ids)
            ? data.recommended_product_ids
                .filter((id: unknown): id is string => typeof id === "string")
                .slice(0, 4)
            : [],
          paypalOfficialLinks:
            data.paypal_offer_context?.official_links &&
            typeof data.paypal_offer_context.official_links === "object"
              ? data.paypal_offer_context.official_links as PayPalOfficialLinks
              : undefined,
          paypalCountryCode:
            typeof data.paypal_offer_context?.country_code === "string"
              ? data.paypal_offer_context.country_code
              : "ZA",
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
      const response = await fetch(apiUrl("/api/assistant"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({ message: text }),
      });

      if (!response.ok) {
        const details = await response.text();
        throw new Error(
          `Assistant request failed (${response.status}): ${details.slice(0, 300)}`
        );
      }

      const data: { reply: string; semantic_response?: SemanticResponse } = await response.json();
      setConversation((items) => [
        ...items,
        { role: "assistant", text: data.reply, semantic: data.semantic_response },
      ]);
    } catch (error) {
      const details =
        error instanceof Error ? error.message : String(error);

      setConversation((items) => [
        ...items,
        {
          role: "assistant",
          text: `Assistant error: ${details}. No payment was made.`,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  async function loadSellerDashboard(requestedId = sellerLookupId) {
    const id = requestedId.trim();
    if (!id) {
      setSellerError("Enter a seller ID to load a store.");
      return;
    }

    setSellerLoading(true);
    setSellerError("");
    setSellerNotice("");

    try {
      const [profileResponse, productsResponse] = await Promise.all([
        fetch(apiUrl(`/api/sellers/${encodeURIComponent(id)}`)),
        fetch(apiUrl(`/api/sellers/${encodeURIComponent(id)}/products?limit=100`)),
      ]);

      const profileData = await profileResponse.json().catch(() => ({}));
      const productsData = await productsResponse.json().catch(() => ({}));

      if (!profileResponse.ok) {
        throw new Error(profileData.detail || "Could not load this seller. Check the seller ID.");
      }
      if (!productsResponse.ok) {
        throw new Error(productsData.detail || "Could not load the seller's products.");
      }

      setSellerProfile(profileData as SellerProfile);
      setSellerProducts(Array.isArray(productsData.products) ? productsData.products : []);
      setSellerLookupId(id);
      setDraftSellerId(id);
    } catch (error) {
      setSellerProfile(null);
      setSellerProducts([]);
      setSellerError(error instanceof Error ? error.message : "Unable to load seller dashboard.");
    } finally {
      setSellerLoading(false);
    }
  }

  async function registerSeller(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSellerRegistering(true);
    setSellerError("");
    setSellerNotice("");

    try {
      const response = await fetch(apiUrl("/api/sellers"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: sellerName.trim(),
          email: sellerEmail.trim(),
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Seller registration failed.");
      }

      setSellerName("");
      setSellerEmail("");
      setSellerLookupId(data.id);
      setSellerNotice(data.message || "Registration submitted for review.");
      await loadSellerDashboard(data.id);
    } catch (error) {
      setSellerError(error instanceof Error ? error.message : "Unable to register seller.");
    } finally {
      setSellerRegistering(false);
    }
  }

  async function submitCustomerAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (authBusy) return;

    setAuthBusy(true);
    setAuthError("");

    try {
      const response = await fetch(
        apiUrl(authMode === "signup" ? "/api/auth/signup" : "/api/auth/login"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: authEmail.trim(),
            password: authPassword,
          }),
        },
      );

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = data.detail;
        throw new Error(
          typeof detail === "string"
            ? detail
            : authMode === "signup"
              ? "Unable to create your account. Check your details and try again."
              : "Unable to sign in. Check your email and password.",
        );
      }

      const result = data as AuthResponse;
      if (!result.access_token || !result.account?.email) {
        throw new Error("The server returned an incomplete authentication response.");
      }

      setAuthToken(result.access_token);
      setAuthAccount(result.account);
      setAuthPassword("");
      setAuthError("");
    } catch (error) {
      setAuthError(
        error instanceof Error
          ? error.message
          : "Unable to connect to PayPilot AI. Please try again.",
      );
    } finally {
      setAuthBusy(false);
    }
  }

  async function logoutCustomer() {
    const token = authToken;
    setAuthToken("");
    setAuthAccount(null);
    setAuthPassword("");
    setAuthMode("login");
    setAuthError("");

    if (token) {
      try {
        await fetch(apiUrl("/api/auth/logout"), {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        // Local logout still takes effect if the network is unavailable.
      }
    }
  }

  if (!authToken || !authAccount) {
    return (
      <main className="auth-screen">
        <section className="auth-card" aria-labelledby="auth-title">
          <a className="auth-brand" href="#" aria-label="PayPilot AI">
            <span className="brand-mark"><Send size={22} strokeWidth={2.5} /></span>
            <span>PayPilot <span className="brand-ai">AI</span></span>
          </a>
          <p className="auth-eyebrow">YOUR SMART MONEY COMPANION</p>
          <h1 id="auth-title">
            {authMode === "signup" ? "Create your account" : "Welcome back"}
          </h1>
          <p className="auth-description">
            {authMode === "signup"
              ? "Create your account to get started with PayPilot AI."
              : "Sign in to continue to your PayPilot AI workspace."}
          </p>

          <form className="auth-form" onSubmit={submitCustomerAuth}>
            <label htmlFor="auth-email">Email address</label>
            <input
              id="auth-email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={authEmail}
              onChange={(event) => setAuthEmail(event.target.value)}
              maxLength={254}
              required
            />
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              type="password"
              autoComplete={authMode === "signup" ? "new-password" : "current-password"}
              placeholder={authMode === "signup" ? "At least 10 characters" : "Enter your password"}
              value={authPassword}
              onChange={(event) => setAuthPassword(event.target.value)}
              minLength={authMode === "signup" ? 10 : 1}
              maxLength={128}
              required
            />
            {authError && <p className="auth-error" role="alert">{authError}</p>}
            <button className="primary-button auth-submit" type="submit" disabled={authBusy}>
              {authBusy
                ? "Please wait…"
                : authMode === "signup"
                  ? "Create account"
                  : "Sign in"}
            </button>
          </form>

          <p className="auth-switch">
            {authMode === "signup" ? "Already have an account?" : "New to PayPilot AI?"}
            {" "}
            <button
              type="button"
              onClick={() => {
                setAuthMode(authMode === "signup" ? "login" : "signup");
                setAuthError("");
              }}
            >
              {authMode === "signup" ? "Sign in" : "Create an account"}
            </button>
          </p>
          <p className="auth-footnote">
            <ShieldCheck size={14} /> Your password is sent to the PayPilot API over the configured connection.
          </p>
        </section>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#dashboard" onClick={() => navigateToSection("dashboard")} aria-label="PayPilot AI home">
          <div className="brand-mark"><Send size={22} strokeWidth={2.5} /></div>
          <span>PayPilot<span className="brand-ai"> AI</span><small>YOUR SMART MONEY COMPANION</small></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>
        <nav className="nav-menu" aria-label="Main navigation">
          <button
            type="button"
            className={`nav-item${activeView === "overview" && activeSection === "dashboard" ? " active" : ""}`}
            aria-current={activeView === "overview" && activeSection === "dashboard" ? "page" : undefined}
            onClick={() => navigateToSection("dashboard")}
          >
            <LayoutDashboard size={18} /> Overview
          </button>
          <button
            type="button"
            className={`nav-item${activeView === "overview" && activeSection === "assistant" ? " active" : ""}`}
            aria-current={activeView === "overview" && activeSection === "assistant" ? "page" : undefined}
            onClick={() => navigateToSection("assistant")}
          >
            <BrainCircuit size={18} /> AI Assistant <span className="nav-badge">AI</span>
          </button>
          <button type="button" className={`nav-item${activeView === "paypal-iq" ? " active" : ""}`} onClick={() => navigateToView("paypal-iq")}>
            <BookOpen size={18} /> PayPal IQ
          </button>
          <button type="button" className={`nav-item${activeView === "seller" ? " active" : ""}`} onClick={() => navigateToView("seller")}>
            <Store size={18} /> Seller Dashboard
          </button>
          <button type="button" className={`nav-item${activeView === "marketplace" ? " active" : ""}`} onClick={() => navigateToView("marketplace")}>
            <ShoppingBag size={18} /> Marketplace
          </button>
          <button type="button" className={`nav-item${activeView === "orders" ? " active" : ""}`} onClick={() => navigateToView("orders")}>
            <Activity size={18} /> Orders
          </button>
          <button type="button" className={`nav-item${activeView === "admin" ? " active" : ""}`} onClick={() => navigateToView("admin")}>
            <ShieldCheck size={18} /> Admin Review
          </button>
          <button
            type="button"
            className={`nav-item${activeView === "overview" && activeSection === "transactions" ? " active" : ""}`}
            onClick={() => navigateToSection("transactions")}
          >
            <Activity size={18} /> Transactions
          </button>
          <button
            type="button"
            className={`nav-item${activeView === "overview" && activeSection === "payments" ? " active" : ""}`}
            onClick={() => navigateToSection("payments")}
          >
            <Wallet size={18} /> Payments
          </button>
        </nav>
        <div className="sidebar-spacer" />
        <div className="upgrade-card">
          <div className="upgrade-icon"><Sparkles size={17} /></div>
          <strong>Your money, made smarter.</strong>
          <p>Let AI take the busywork out of payments.</p>
          <span className="upgrade-link">Explore PayPilot <ArrowUpRight size={14} /></span>
        </div>
        <div className="profile-row">
          <div className="avatar profile-avatar">{authAccount.email.slice(0, 1).toUpperCase()}</div>
          <div className="profile-info"><strong>{authAccount.email}</strong><span>Personal account</span></div>
          <button type="button" className="auth-logout" onClick={logoutCustomer}>Log out</button>
        </div>
      </aside>

      <main className="main-area" id="dashboard">
        <header className="topbar">
                    <div className="breadcrumb">
            Workspace <span>/</span>{" "}
            <strong>
              {activeView === "overview"
                ? activeSection === "assistant"
                  ? "AI Assistant"
                  : activeSection === "transactions"
                    ? "Transactions"
                    : activeSection === "payments"
                      ? "Payments"
                      : "Overview"
                : activeView === "marketplace"
                  ? "Marketplace"
                  : activeView === "orders"
                    ? "Orders"
                    : activeView === "seller"
                      ? "Seller Dashboard"
                      : "Admin Review"}
            </strong>
          </div>
          <div className="topbar-actions">
            <div className="sandbox-pill"><span /> SANDBOX MODE</div>
            <button className="icon-button" aria-label="Notifications"><Bell size={18} /><i /></button>
            <div className="avatar top-avatar" title={authAccount.email}>{authAccount.email.slice(0, 1).toUpperCase()}</div>
          </div>
        </header>

        {marketplaceNotice && (
          <div
            className="marketplace-message"
            role={marketplaceNoticeType === "error" ? "alert" : "status"}
            aria-live={marketplaceNoticeType === "error" ? "assertive" : "polite"}
            style={{
              margin: "16px 0",
              borderLeft: `4px solid ${
                marketplaceNoticeType === "error"
                  ? "#b42318"
                  : marketplaceNoticeType === "success"
                    ? "#067647"
                    : "#64748b"
              }`,
              padding: "12px 16px",
            }}
          >
            {marketplaceNotice}
          </div>
        )}

        <div className="page-content">

  {activeView === "orders" && (
    <section className="marketplace-view" id="orders">
      <div className="marketplace-hero">
        <div>
          <span className="marketplace-eyebrow">PAYPILOT COMMERCE</span>
          <h1>Order history</h1>
          <p>Review recent marketplace purchases and their payment status.</p>
        </div>
        <button
          type="button"
          className="marketplace-secondary-button"
          onClick={() => setOrdersReload((value) => value + 1)}
          disabled={ordersLoading}
        >
          <RefreshCw size={16} /> Refresh orders
        </button>
      </div>

      {ordersLoading && (
        <div className="marketplace-message">Loading marketplace orders...</div>
      )}

      {!ordersLoading && ordersError && (
        <div className="marketplace-message" role="alert">
          <p>{ordersError}</p>
          <button
            type="button"
            onClick={() => setOrdersReload((value) => value + 1)}
          >
            Try again
          </button>
        </div>
      )}

      {!ordersLoading && !ordersError && orders.length === 0 && (
        <div className="marketplace-message">
          <h2>No orders yet</h2>
          <p>Marketplace purchases will appear here after checkout.</p>
        </div>
      )}

      {!ordersLoading && !ordersError && orders.length > 0 && (
        <div style={{ display: "grid", gap: 16, marginTop: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            <div>
              <h2 style={{ margin: 0 }}>Recent orders</h2>
              <p style={{ margin: "6px 0 0", color: "var(--text-muted, #737789)" }}>
                {orders.length} order{orders.length === 1 ? "" : "s"} loaded
              </p>
            </div>
            <strong>
              {formatMoney(
                orders
                  .filter((order) => order.status === "COMPLETED")
                  .reduce((total, order) => total + order.amount_minor, 0) / 100,
                orders.find((order) => order.status === "COMPLETED")?.currency || "USD"
              )} completed order value
            </strong>
          </div>

          {orders.map((order) => (
            <article
              key={order.id}
              style={{
                background: "var(--panel, #ffffff)",
                border: "1px solid var(--border, #e7e8ee)",
                borderRadius: 16,
                padding: 20,
                display: "grid",
                gap: 14,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
                <div>
                  <h3 style={{ margin: "0 0 6px" }}>
                    Order #{order.id.slice(0, 8)}
                  </h3>
                  <p style={{ margin: 0, color: "var(--text-muted, #737789)", fontSize: 13 }}>
                    {formatTransactionDate(order.created_at)}
                  </p>
                </div>
                <span
                  style={{
                    display: "inline-block",
                    borderRadius: 999,
                    padding: "6px 11px",
                    fontSize: 12,
                    fontWeight: 700,
                    background: order.status === "COMPLETED" ? "#e7f8ee" : "#fff3d6",
                    color: order.status === "COMPLETED" ? "#18794e" : "#8a5a00",
                  }}
                >
                  {order.status}
                </span>
              </div>

              <div style={{ display: "grid", gap: 12 }}>
                {order.items.map((item) => (
                  <div
                    key={`${order.id}-${item.product_id}`}
                    style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}
                  >
                    <div>
                      <strong>{item.product_name}</strong>
                      <p style={{ margin: "5px 0 0", color: "var(--text-muted, #737789)", fontSize: 13 }}>
                        Qty {item.quantity} ? {formatMoney(item.unit_price_minor / 100, order.currency)}
                      </p>
                    </div>
                    <strong>
                      {formatMoney(item.line_total_minor / 100, order.currency)}
                    </strong>
                  </div>
                ))}
              </div>

              <div style={{ borderTop: "1px solid var(--border, #e7e8ee)", paddingTop: 14, display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <span style={{ color: "var(--text-muted, #737789)", fontSize: 12 }}>PayPal order reference</span>
                  <div style={{ fontSize: 13, overflowWrap: "anywhere" }}>{order.paypal_order_id}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span style={{ color: "var(--text-muted, #737789)", fontSize: 12 }}>Order total</span>
                  <div style={{ fontSize: 20, fontWeight: 750 }}>
                    {formatMoney(order.amount_minor / 100, order.currency)}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="marketplace-product-note" style={{ marginTop: 20 }}>
        Internal demo order history. Customer accounts and private, buyer-specific order access are not implemented yet. Payments shown here are from PayPal Sandbox.
      </p>
    </section>
  )}

  {activeView === "seller" && (
    <section className="marketplace-view" id="seller-dashboard">
      <div className="marketplace-hero">
        <div>
          <span className="marketplace-eyebrow">PAYPILOT COMMERCE</span>
          <h1>Seller Dashboard</h1>
          <p>Register your store, track approval, and manage your product submissions.</p>
        </div>
        <div className="marketplace-hero-icon"><Store size={28} /></div>
      </div>

      <section style={{ margin: "20px 0", padding: 24, border: "1px solid var(--border, #e7e8ef)", borderRadius: 18, background: "var(--surface, #fff)" }}>
        <h2 style={{ marginTop: 0 }}>Register your store</h2>
        <p style={{ color: "var(--text-muted, #737789)" }}>
          New sellers start as pending. An administrator must approve the store before it can submit product listings.
        </p>
        <form onSubmit={registerSeller} style={{ display: "grid", gap: 12 }}>
          <label style={{ display: "grid", gap: 6 }}>
            Store name
            <input value={sellerName} onChange={(event) => setSellerName(event.target.value)} required minLength={2} maxLength={120} placeholder="e.g. Darchums Store" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
          </label>
          <label style={{ display: "grid", gap: 6 }}>
            Contact email
            <input type="email" value={sellerEmail} onChange={(event) => setSellerEmail(event.target.value)} required placeholder="you@example.com" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
          </label>
          <button type="submit" disabled={sellerRegistering} className="primary-button" style={{ justifySelf: "start", padding: "10px 16px", borderRadius: 9 }}>
            {sellerRegistering ? "Registering..." : "Register store"}
          </button>
        </form>
      </section>

      <section style={{ margin: "20px 0", padding: 24, border: "1px solid var(--border, #e7e8ef)", borderRadius: 18, background: "var(--surface, #fff)" }}>
        <h2 style={{ marginTop: 0 }}>Load your store</h2>
        <p style={{ color: "var(--text-muted, #737789)" }}>Enter your seller ID to view its approval status and product listings.</p>
        <form onSubmit={(event) => { event.preventDefault(); void loadSellerDashboard(); }} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <input aria-label="Seller ID" value={sellerLookupId} onChange={(event) => setSellerLookupId(event.target.value)} required placeholder="Seller ID" style={{ flex: "1 1 300px", minWidth: 0, padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
          <button type="submit" disabled={sellerLoading} className="primary-button" style={{ padding: "10px 16px", borderRadius: 9 }}>
            {sellerLoading ? "Loading..." : "Load store"}
          </button>
        </form>
      </section>

      {sellerNotice && (
        <div role="status" style={{ margin: "16px 0", padding: 14, borderRadius: 10, background: "#ecfdf3", color: "#166534" }}>
          {sellerNotice}
        </div>
      )}
      {sellerError && (
        <div role="alert" style={{ margin: "16px 0", padding: 14, borderRadius: 10, background: "#fef2f2", color: "#b91c1c" }}>
          {sellerError}
        </div>
      )}

      {sellerProfile && (
        <>
          <section style={{ margin: "20px 0", padding: 24, border: "1px solid var(--border, #e7e8ef)", borderRadius: 18, background: "var(--surface, #fff)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
              <div>
                <span className="marketplace-eyebrow">YOUR STORE</span>
                <h2 style={{ margin: "6px 0" }}>{sellerProfile.display_name}</h2>
                <p style={{ margin: "4px 0", color: "var(--text-muted, #737789)" }}>{sellerProfile.email}</p>
                <p style={{ margin: "8px 0", fontSize: 12, overflowWrap: "anywhere" }}>Seller ID: {sellerProfile.id}</p>
              </div>
              <span style={{ display: "inline-block", padding: "7px 12px", borderRadius: 999, fontWeight: 700, fontSize: 12, background: sellerProfile.status === "ACTIVE" ? "#dcfce7" : sellerProfile.status === "SUSPENDED" ? "#fee2e2" : "#fef3c7", color: sellerProfile.status === "ACTIVE" ? "#166534" : sellerProfile.status === "SUSPENDED" ? "#991b1b" : "#92400e" }}>
                {sellerProfile.status}
              </span>
            </div>
            {sellerProfile.status !== "ACTIVE" && (
              <p style={{ marginBottom: 0, color: "var(--text-muted, #737789)" }}>
                {sellerProfile.status === "PENDING" ? "Your store is awaiting administrator approval. You can view the dashboard while you wait." : "Your store is currently suspended. Contact the administrator for assistance."}
              </p>
            )}
            {sellerProfile.status === "ACTIVE" && (
              <p style={{ marginBottom: 0, color: "var(--text-muted, #737789)" }}>
                Your store is approved. To add a product, open Marketplace and submit a listing using this seller ID. New listings remain drafts until an administrator publishes them.
              </p>
            )}
          </section>

          {/* SELLER_DASHBOARD_PRODUCT_FORM */}
          {sellerProfile.status === "ACTIVE" && (
            <section style={{ margin: "20px 0", padding: 24, border: "1px solid var(--border, #e7e8ef)", borderRadius: 18, background: "var(--surface, #fff)" }}>
              <h2 style={{ marginTop: 0 }}>Add a product</h2>
              <p style={{ color: "var(--text-muted, #737789)" }}>
                Submit a product for review. It remains a draft until an administrator publishes it.
              </p>

              <form onSubmit={submitProductDraft} style={{ display: "grid", gap: 14 }}>
                <label style={{ display: "grid", gap: 6 }}>
                  Product name
                  <input value={draftName} onChange={(event) => setDraftName(event.target.value)} required minLength={2} maxLength={160} placeholder="e.g. Wireless headphones" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  Description
                  <textarea value={draftDescription} onChange={(event) => setDraftDescription(event.target.value)} maxLength={2000} rows={3} placeholder="Describe your product" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5", resize: "vertical" }} />
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  Category
                  <input value={draftCategory} onChange={(event) => setDraftCategory(event.target.value)} required maxLength={80} placeholder="e.g. Electronics" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
                </label>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 14 }}>
                  <label style={{ display: "grid", gap: 6 }}>
                    Price (USD)
                    <input type="number" value={draftPrice} onChange={(event) => setDraftPrice(event.target.value)} required min="0.01" max="1000000" step="0.01" placeholder="19.99" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
                  </label>
                  <label style={{ display: "grid", gap: 6 }}>
                    Inventory quantity
                    <input type="number" value={draftStock} onChange={(event) => setDraftStock(event.target.value)} required min="0" max="100000" step="1" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
                  </label>
                </div>

                <label style={{ display: "grid", gap: 6 }}>
                  Product image URL (optional)
                  <input type="url" value={draftImageUrl} onChange={(event) => setDraftImageUrl(event.target.value)} maxLength={1000} placeholder="https://example.com/product.jpg" style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }} />
                </label>

                {draftNotice && (
                  <p role={draftNoticeType === "error" ? "alert" : "status"} style={{ margin: 0, padding: 12, borderRadius: 9, background: draftNoticeType === "error" ? "#fef2f2" : "#f0fdf4", color: draftNoticeType === "error" ? "#b91c1c" : "#166534" }}>
                    {draftNotice}
                  </p>
                )}

                <button type="submit" disabled={draftSubmitting} style={{ padding: "12px 16px", borderRadius: 10, border: 0, cursor: draftSubmitting ? "wait" : "pointer", maxWidth: 260 }}>
                  <Plus size={16} style={{ verticalAlign: "middle", marginRight: 8 }} />
                  {draftSubmitting ? "Saving draft..." : "Submit product draft"}
                </button>
              </form>
            </section>
          )}
          <section style={{ margin: "20px 0", padding: 24, border: "1px solid var(--border, #e7e8ef)", borderRadius: 18, background: "var(--surface, #fff)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <div>
                <h2 style={{ margin: 0 }}>Your products</h2>
                <p style={{ margin: "5px 0 0", color: "var(--text-muted, #737789)" }}>{sellerProducts.length} listing(s), including drafts and archived products.</p>
              </div>
              <button type="button" onClick={() => void loadSellerDashboard(sellerProfile.id)} disabled={sellerLoading} style={{ padding: "9px 12px", borderRadius: 9, border: "1px solid #d9dce5", background: "transparent", cursor: "pointer" }}>
                <RefreshCw size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Refresh
              </button>
            </div>

            {sellerProducts.length === 0 ? (
              <p style={{ marginTop: 20, color: "var(--text-muted, #737789)" }}>No products found for this store yet.</p>
            ) : (
              <div style={{ display: "grid", gap: 12, marginTop: 18 }}>
                {sellerProducts.map((product) => (
                  <article key={product.id} style={{ display: "flex", gap: 14, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", padding: 16, border: "1px solid var(--border, #e7e8ef)", borderRadius: 12 }}>
                    <div style={{ minWidth: 0, flex: "1 1 220px" }}>
                      <strong>{product.name}</strong>
                      <p style={{ margin: "5px 0", color: "var(--text-muted, #737789)" }}>{product.category} ? Stock: {product.inventory_quantity}</p>
                      <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted, #737789)" }}>{product.description || "No description provided."}</p>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <strong>{formatMoney(product.price_minor / 100, product.currency)}</strong>
                      <div style={{ marginTop: 6, fontSize: 12, fontWeight: 700, color: product.status === "ACTIVE" ? "#15803d" : product.status === "ARCHIVED" ? "#b91c1c" : "#92400e" }}>
                        {product.status}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <p className="marketplace-product-note" style={{ marginTop: 20 }}>
        Demo limitation: seller IDs are not authentication. Do not use this dashboard for real seller data or production operations until seller login and server-side ownership checks are implemented.
      </p>
    </section>
  )}

  {activeView === "admin" && (
    <section className="marketplace-view" id="admin-review">
      <div className="marketplace-hero">
        <div>
          <span className="marketplace-eyebrow">PAYPILOT COMMERCE</span>
          <h1>Product review</h1>
          <p>Review seller submissions before they appear in the public marketplace.</p>
        </div>
        <div className="marketplace-hero-icon"><ShieldCheck size={28} /></div>
      </div>

      <section
        aria-labelledby="admin-access-title"
        style={{
          margin: "20px 0",
          padding: 24,
          border: "1px solid var(--border, #e7e8ef)",
          borderRadius: 18,
          background: "var(--surface, #fff)",
        }}
      >
        <h2 id="admin-access-title" style={{ marginTop: 0 }}>Administrator access</h2>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void Promise.all([loadAdminDrafts(), loadAdminSellers()]);
          }}
          style={{ display: "grid", gap: 12 }}
        >
          <label style={{ display: "grid", gap: 6 }}>
            Admin token
            <input
              type="password"
              value={adminToken}
              onChange={(event) => setAdminToken(event.target.value)}
              autoComplete="off"
              required
              placeholder="Enter the token configured in backend/.env"
              style={{
                width: "100%",
                padding: 11,
                borderRadius: 9,
                border: "1px solid #d9dce5",
              }}
            />
          </label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <button
              type="submit"
              className="marketplace-add-to-cart"
              disabled={adminLoading || !adminToken.trim()}
            >
              <RefreshCw size={16} />
              {adminLoading ? "Loading submissions..." : "Unlock & load drafts"}
            </button>
            <button
              type="button"
              className="marketplace-refresh"
              onClick={() => {
                setAdminToken("");
                setAdminDrafts([]);
                setAdminSellers([]);
                setAdminError("");
                setAdminNotice("");
              }}
            >
              Lock & clear token
            </button>
          </div>
        </form>
        <p style={{ marginBottom: 0, fontSize: 12, color: "var(--text-muted, #737789)" }}>
          Local hackathon demo only. The token is held in page memory and sent to the
          backend in request headers. This is not a substitute for production admin
          authentication, user sessions, or role-based access control.
        </p>
      </section>

      {adminError && (
        <div className="marketplace-error" role="alert">
          <p>{adminError}</p>
        </div>
      )}

      {adminNotice && (
        <p role="status" style={{ color: "#067647" }}>{adminNotice}</p>
      )}

      {adminToken.trim() && (
        <section
          aria-labelledby="seller-applications-title"
          style={{
            margin: "20px 0",
            padding: 24,
            border: "1px solid var(--border, #e7e8ef)",
            borderRadius: 18,
            background: "var(--surface, #fff)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <div>
              <h2 id="seller-applications-title" style={{ margin: 0 }}>Seller Applications</h2>
              <p style={{ margin: "5px 0 0", color: "var(--text-muted, #737789)" }}>
                {adminSellers.length} pending application(s). Approve a store before it can submit products.
              </p>
            </div>
            <button
              type="button"
              className="marketplace-refresh"
              onClick={() => void loadAdminSellers()}
              disabled={adminSellersLoading}
            >
              <RefreshCw size={16} /> {adminSellersLoading ? "Refreshing..." : "Refresh sellers"}
            </button>
          </div>

          {adminSellersLoading ? (
            <p style={{ marginTop: 18 }}>Loading seller applications...</p>
          ) : adminSellers.length === 0 ? (
            <div className="marketplace-empty" style={{ marginTop: 18 }}>
              <div className="marketplace-empty-icon"><CheckCircle2 size={30} /></div>
              <h3>No pending seller applications</h3>
              <p>New registrations will appear here after you refresh.</p>
            </div>
          ) : (
            <div style={{ display: "grid", gap: 14, marginTop: 20 }}>
              {adminSellers.map((seller) => (
                <article
                  key={seller.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 16,
                    flexWrap: "wrap",
                    padding: 18,
                    border: "1px solid var(--border, #e7e8ef)",
                    borderRadius: 12,
                  }}
                >
                  <div style={{ minWidth: 0, flex: "1 1 240px" }}>
                    <strong>{seller.display_name}</strong>
                    <p style={{ margin: "5px 0", color: "var(--text-muted, #737789)" }}>{seller.email}</p>
                    <p style={{ margin: "5px 0", fontSize: 12, overflowWrap: "anywhere" }}>ID: {seller.id}</p>
                    {seller.created_at && (
                      <p style={{ margin: "5px 0", fontSize: 12, color: "var(--text-muted, #737789)" }}>
                        Registered: {new Date(seller.created_at).toLocaleString()}
                      </p>
                    )}
                    <span style={{ display: "inline-block", marginTop: 5, padding: "5px 9px", borderRadius: 999, background: "#fef3c7", color: "#92400e", fontSize: 11, fontWeight: 700 }}>
                      {seller.status}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="marketplace-primary-button"
                    disabled={Boolean(adminBusySellerId)}
                    onClick={() => void approveSellerApplication(seller)}
                    style={{ padding: "10px 14px", borderRadius: 9 }}
                  >
                    <CheckCircle2 size={16} style={{ verticalAlign: "middle", marginRight: 6 }} />
                    {adminBusySellerId === seller.id ? "Approving..." : "Approve Seller"}
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {adminToken.trim() && (
        <section
          aria-labelledby="pending-drafts-title"
          style={{
            margin: "20px 0",
            padding: 24,
            border: "1px solid var(--border, #e7e8ef)",
            borderRadius: 18,
            background: "var(--surface, #fff)",
          }}
        >
          <div style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
          }}>
            <div>
              <h2 id="pending-drafts-title" style={{ margin: 0 }}>Pending submissions</h2>
              <p style={{ margin: "5px 0 0", color: "var(--text-muted, #737789)" }}>
                {adminDrafts.length} draft{adminDrafts.length === 1 ? "" : "s"} loaded
              </p>
            </div>
            <button
              type="button"
              className="marketplace-refresh"
              onClick={() => void loadAdminDrafts()}
              disabled={adminLoading}
            >
              <RefreshCw size={16} /> Refresh drafts
            </button>
          </div>

          {adminLoading ? (
            <p>Loading product submissions...</p>
          ) : adminDrafts.length === 0 ? (
            <div className="marketplace-empty" style={{ marginTop: 18 }}>
              <div className="marketplace-empty-icon"><CheckCircle2 size={30} /></div>
              <h2>No pending drafts</h2>
              <p>New product submissions will appear here when you refresh the list.</p>
            </div>
          ) : (
            <div style={{ display: "grid", gap: 16, marginTop: 20 }}>
              {adminDrafts.map((product) => (
                <article
                  key={product.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(0, 1fr)",
                    gap: 12,
                    padding: 18,
                    border: "1px solid #e7e8ef",
                    borderRadius: 14,
                  }}
                >
                  <div style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: 12,
                    flexWrap: "wrap",
                  }}>
                    <div>
                      <span className="marketplace-category-tag">
                        {product.category || "General"}
                      </span>
                      <h3 style={{ margin: "8px 0" }}>{product.name}</h3>
                      <p style={{ margin: 0, color: "var(--text-muted, #737789)" }}>
                        {product.description || "No description provided."}
                      </p>
                    </div>
                    <strong>
                      {formatMoney(product.price_minor / 100, product.currency)}
                    </strong>
                  </div>

                  {product.image_url && (
                    <p style={{ margin: 0 }}>
                      <a href={product.image_url} target="_blank" rel="noreferrer">
                        View product image
                      </a>
                    </p>
                  )}

                  <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                    gap: 10,
                    fontSize: 13,
                  }}>
                    <div><strong>Seller</strong><br />{product.seller_name}</div>
                    <div><strong>Seller email</strong><br />{product.seller_email}</div>
                    <div><strong>Seller status</strong><br />{product.seller_status}</div>
                    <div><strong>Stock</strong><br />{product.inventory_quantity}</div>
                    <div><strong>Submission status</strong><br />{product.status}</div>
                  </div>

                  {product.seller_status !== "ACTIVE" && (
                    <p role="alert" style={{ color: "#b54708", margin: 0 }}>
                      This seller is not active. Activate the seller before publishing
                      this product.
                    </p>
                  )}
                  {product.inventory_quantity < 1 && (
                    <p role="alert" style={{ color: "#b54708", margin: 0 }}>
                      This product has no stock and cannot be published.
                    </p>
                  )}

                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                    <button
                      type="button"
                      className="marketplace-add-to-cart"
                      disabled={
                        Boolean(adminBusyProductId) ||
                        product.seller_status !== "ACTIVE" ||
                        product.inventory_quantity < 1
                      }
                      onClick={() => void reviewProduct(product, "publish")}
                    >
                      <CheckCircle2 size={16} />
                      {adminBusyProductId === product.id ? "Processing..." : "Approve & Publish"}
                    </button>
                    <button
                      type="button"
                      className="marketplace-refresh"
                      disabled={Boolean(adminBusyProductId)}
                      onClick={() => void reviewProduct(product, "reject")}
                    >
                      <Trash2 size={16} /> Reject & Archive
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </section>
  )}

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

      <section
        aria-labelledby="add-product-title"
        style={{
          margin: "20px 0",
          padding: 24,
          border: "1px solid var(--border, #e7e8ef)",
          borderRadius: 18,
          background: "var(--surface, #fff)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
          <div className="marketplace-hero-icon"><Plus size={24} /></div>
          <div>
            <h2 id="add-product-title" style={{ margin: 0 }}>Add a product</h2>
            <p style={{ margin: "5px 0 0", color: "var(--text-muted, #737789)" }}>
              Submit a listing for administrator review.
            </p>
          </div>
        </div>

        <form onSubmit={submitProductDraft} style={{ display: "grid", gap: 14 }}>
          <label style={{ display: "grid", gap: 6 }}>
            Demo seller ID
            <input
              value={draftSellerId}
              onChange={(event) => setDraftSellerId(event.target.value)}
              required
              aria-label="Demo seller ID"
              style={{ width: "100%", padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }}
            />
          </label>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
            <label style={{ display: "grid", gap: 6 }}>
              Product name
              <input
                value={draftName}
                onChange={(event) => setDraftName(event.target.value)}
                minLength={2}
                maxLength={120}
                required
                placeholder="e.g. Wireless keyboard"
                style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }}
              />
            </label>
            <label style={{ display: "grid", gap: 6 }}>
              Category
              <input
                value={draftCategory}
                onChange={(event) => setDraftCategory(event.target.value)}
                minLength={2}
                maxLength={80}
                required
                placeholder="Electronics"
                style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }}
              />
            </label>
            <label style={{ display: "grid", gap: 6 }}>
              Price (USD)
              <input
                type="number"
                value={draftPrice}
                onChange={(event) => setDraftPrice(event.target.value)}
                min="0.01"
                max="99999999"
                step="0.01"
                required
                placeholder="29.99"
                style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }}
              />
            </label>
            <label style={{ display: "grid", gap: 6 }}>
              Stock quantity
              <input
                type="number"
                value={draftStock}
                onChange={(event) => setDraftStock(event.target.value)}
                min="0"
                max="100000"
                step="1"
                required
                style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }}
              />
            </label>
          </div>

          <label style={{ display: "grid", gap: 6 }}>
            Description
            <textarea
              value={draftDescription}
              onChange={(event) => setDraftDescription(event.target.value)}
              maxLength={3000}
              rows={3}
              placeholder="Describe the product and its features."
              style={{ width: "100%", padding: 11, borderRadius: 9, border: "1px solid #d9dce5", resize: "vertical" }}
            />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            Product image URL (optional)
            <input
              type="url"
              value={draftImageUrl}
              onChange={(event) => setDraftImageUrl(event.target.value)}
              maxLength={1000}
              placeholder="https://example.com/product.jpg"
              style={{ padding: 11, borderRadius: 9, border: "1px solid #d9dce5" }}
            />
          </label>

          {draftNotice && (
            <p
              role={draftNoticeType === "error" ? "alert" : "status"}
              style={{
                margin: 0,
                color: draftNoticeType === "error" ? "#b42318" : "#067647",
              }}
            >
              {draftNotice}
            </p>
          )}

          <button
            type="submit"
            className="marketplace-add-to-cart"
            disabled={draftSubmitting}
            style={{ justifyContent: "center", maxWidth: 260 }}
          >
            <Plus size={16} />
            {draftSubmitting ? "Saving draft..." : "Submit product draft"}
          </button>

          <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted, #737789)" }}>
            Local demo only. This form uses the existing demo seller. Seller authentication
            is not implemented, and submitting a draft does not publish it.
          </p>
        </form>
      </section>

      <div className="marketplace-cart-summary" aria-live="polite">
        <div className="marketplace-cart-heading">
          <ShoppingCart size={20} />
          <div>
            <h2>Your cart <span>({cartCount})</span></h2>
            <p>Review your selected marketplace items.</p>
          </div>
        </div>

        {cartItems.length === 0 ? (
          <p className="marketplace-cart-empty">Your cart is empty. Add a product to get started.</p>
        ) : (
          <>
            <div className="marketplace-cart-items">
              {cartItems.map((item) => (
                <div className="marketplace-cart-item" key={item.product.id}>
                  <div className="marketplace-cart-item-info">
                    <strong>{item.product.name}</strong>
                    <span>{formatMoney(item.product.price, item.product.currency)} each</span>
                  </div>
                  <div className="marketplace-cart-controls">
                    <button
                      type="button"
                      aria-label={`Remove one ${item.product.name}`}
                      onClick={() => changeCartQuantity(item.product.id, -1)}
                    >
                      <Minus size={14} />
                    </button>
                    <span>{item.quantity}</span>
                    <button
                      type="button"
                      aria-label={`Add one ${item.product.name}`}
                      disabled={item.quantity >= item.product.inventory_quantity}
                      onClick={() => changeCartQuantity(item.product.id, 1)}
                    >
                      <Plus size={14} />
                    </button>
                    <button
                      type="button"
                      className="marketplace-cart-remove"
                      aria-label={`Remove ${item.product.name} from cart`}
                      onClick={() => removeFromCart(item.product.id)}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <strong className="marketplace-cart-line-total">
                    {formatMoney((item.product.price_minor * item.quantity) / 100, item.product.currency)}
                  </strong>
                </div>
              ))}
            </div>
            <div className="marketplace-cart-total">
              <span>Estimated total</span>
              <strong>{formatMoney(cartTotalMinor / 100, cartItems[0]?.product.currency || "USD")}</strong>
            </div>
            <button
              type="button"
              className="marketplace-checkout-button"
              onClick={handleMarketplaceCheckout}
              disabled={cartItems.length === 0 || marketplaceCheckoutBusy}
            >
              {marketplaceCheckoutBusy
                ? "Processing checkout..."
                : `Checkout with PayPal - ${formatMoney(
                    cartTotalMinor / 100,
                    cartItems[0]?.product.currency || "USD"
                  )}`}
            </button>
            <p className="marketplace-cart-note">
              Pay securely through PayPal Sandbox. Your cart remains available if checkout is cancelled.
            </p>
          </>
        )}
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
                  <button
                    type="button"
                    className="marketplace-add-to-cart"
                    disabled={
                      product.inventory_quantity < 1 ||
                      (cartItems.find((item) => item.product.id === product.id)?.quantity ?? 0) >= product.inventory_quantity
                    }
                    onClick={() => addToCart(product)}
                  >
                    <ShoppingCart size={15} />
                    {(cartItems.find((item) => item.product.id === product.id)?.quantity ?? 0) >= product.inventory_quantity
                      ? "Stock limit reached"
                      : "Add to cart"}
                  </button>
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
              <div className="marketplace-chat-content">
                <p className="marketplace-chat-bubble">{item.text}</p>
                {item.role === "assistant" && <SemanticDetails semantic={item.semantic} />}

                {item.role === "assistant" && item.paypalOfficialLinks ? (
                  <section className="paypal-promo-panel" aria-label="Official PayPal resources">
                    <div className="paypal-promo-heading">
                      <strong>Explore PayPal</strong>
                      <span>
                        Official PayPal resources
                        <span className="paypal-promo-country">{item.paypalCountryCode || "ZA"}</span>
                      </span>
                    </div>
                    <p>
                      Discover PayPal account and business services directly on PayPal.
                      Availability and eligibility depend on your country.
                    </p>
                    <div className="paypal-promo-links">
                      {([
                        ["account", "Create a PayPal account"],
                        ["business", "Open a PayPal Business account"],
                        ["sign_in", "Sign in to PayPal"],
                      ] as const).map(([key, label]) => {
                        const url = item.paypalOfficialLinks?.[key];
                        if (!url) return null;
                        return (
                          <button
                            type="button"
                            key={key}
                            className="paypal-promo-link"
                            onClick={() =>
                              void openPayPalResource(
                                key,
                                url,
                                item.paypalCountryCode || "ZA"
                              )
                            }
                          >
                            {label} <span aria-hidden="true">?</span>
                          </button>
                        );
                      })}
                    </div>
                    <small className="paypal-promo-disclaimer">
                      PayPilot AI is an independent platform. These links lead to PayPal;
                      no special discount or partnership is implied.
                    </small>
                  </section>
                ) : null}

                {item.role === "assistant" && item.recommendedProductIds?.length ? (
                  <div className="marketplace-recommendations">
                    <p className="marketplace-recommendations-heading">
                      Recommended marketplace listings
                    </p>
                    <div className="marketplace-recommendation-grid">
                      {item.recommendedProductIds.map((productId) => {
                        const product = products.find(
                          (candidate) => candidate.id === productId
                        );

                        if (!product) return null;

                        const cartQuantity =
                          cartItems.find(
                            (cartItem) => cartItem.product.id === product.id
                          )?.quantity ?? 0;

                        const stockLimitReached =
                          product.inventory_quantity < 1 ||
                          cartQuantity >= product.inventory_quantity;

                        return (
                          <article
                            className="marketplace-recommendation-card"
                            key={product.id}
                          >
                            {product.image_url ? (
                              <img
                                src={product.image_url}
                                alt={product.name}
                                onError={(event) => {
                                  event.currentTarget.style.display = "none";
                                }}
                              />
                            ) : (
                              <div className="marketplace-recommendation-placeholder">
                                <ShoppingBag size={23} />
                              </div>
                            )}

                            <div className="marketplace-recommendation-body">
                              <span>{product.category || "General"}</span>
                              <strong>{product.name}</strong>
                              <small>Sold by {product.seller_name}</small>
                              <div className="marketplace-recommendation-price">
                                <strong>
                                  {formatMoney(product.price, product.currency)}
                                </strong>
                                <small>{product.inventory_quantity} available</small>
                              </div>
                              <button
                                type="button"
                                className="marketplace-add-to-cart"
                                disabled={stockLimitReached}
                                onClick={() => addToCart(product)}
                              >
                                <ShoppingCart size={15} />
                                {stockLimitReached
                                  ? "Stock limit reached"
                                  : "Add to cart"}
                              </button>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
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
          Recommendations are based on current marketplace listings. Checkout is handled through PayPal Sandbox.
          The assistant cannot create or capture payments.
        </p>
      </section>

      <p className="marketplace-product-note">
        Marketplace checkout is in testing. Payments use PayPal Sandbox; multi-seller payouts are not yet implemented.
      </p>
    </section>
  )}

  {activeView === "paypal-iq" && (
    <section className="paypal-iq-view">
      <div className="paypal-iq-hero">
        <div>
          <span className="paypal-iq-eyebrow">PAYPILOT AI LEARNING</span>
          <h1>PayPal IQ</h1>
          <p>Build your payment knowledge. Learn a fact, take the daily challenge, and track your progress.</p>
        </div>
        <div className="paypal-iq-hero-icon">
          <BookOpen size={34} />
        </div>
      </div>

      {paypalIQLoading && (
        <div className="panel paypal-iq-message">Loading your PayPal IQ learning dashboard...</div>
      )}

      {paypalIQError && (
        <div className="panel paypal-iq-error">
          <p>{paypalIQError}</p>
          <button type="button" onClick={() => setActiveView("overview")}>Return to dashboard</button>
        </div>
      )}

      {!paypalIQLoading && !paypalIQError && (
        <>
          <div className="paypal-iq-stats">
            <article className="paypal-iq-stat">
              <Award size={21} />
              <span>Total points</span>
              <strong>{paypalIQProgress?.total_points ?? 0}</strong>
            </article>
            <article className="paypal-iq-stat">
              <Flame size={21} />
              <span>Current streak</span>
              <strong>{paypalIQProgress?.current_streak ?? 0} days</strong>
            </article>
            <article className="paypal-iq-stat">
              <CheckCircle2 size={21} />
              <span>Quizzes completed</span>
              <strong>{paypalIQProgress?.quizzes_completed ?? 0}</strong>
            </article>
            <article className="paypal-iq-stat">
              <BookOpen size={21} />
              <span>Facts viewed</span>
              <strong>{paypalIQProgress?.facts_viewed ?? 0}</strong>
            </article>
          </div>

          <section className="panel paypal-iq-daily">
            <div className="paypal-iq-section-heading">
              <div>
                <span className="paypal-iq-eyebrow">TODAY'S LEARNING</span>
                <h2>Daily PayPal fact</h2>
              </div>
              <span className="paypal-iq-points">+2 points</span>
            </div>

            {paypalIQDailyFact ? (
              <article className="paypal-iq-fact-card">
                <span className="paypal-iq-category">{paypalIQDailyFact.category}</span>
                <h3>{paypalIQDailyFact.title}</h3>
                <p>{paypalIQDailyFact.fact_text}</p>
                {paypalIQDailyFact.explanation && (
                  <p className="paypal-iq-explanation">{paypalIQDailyFact.explanation}</p>
                )}
                <div className="paypal-iq-source">
                  <ShieldCheck size={15} />
                  <span>
                    {paypalIQDailyFact.source_title || "Verified source"}
                    {paypalIQDailyFact.verified_at
                      ? ` · Verified ${paypalIQDailyFact.verified_at.slice(0, 10)}`
                      : ""}
                  </span>
                  {paypalIQDailyFact.source_url && (
                    <a href={paypalIQDailyFact.source_url} target="_blank" rel="noreferrer">
                      View source
                    </a>
                  )}
                </div>
              </article>
            ) : (
              <p>No published daily fact is available yet.</p>
            )}
          </section>

          <section className="panel paypal-iq-quiz">
            <div className="paypal-iq-section-heading">
              <div>
                <span className="paypal-iq-eyebrow">DAILY CHALLENGE</span>
                <h2>Test your knowledge</h2>
                <p>Answer the questions and receive feedback from the learning engine.</p>
              </div>
              <span className="paypal-iq-quiz-count">
                {paypalIQQuestions.length} questions
              </span>
            </div>

            {paypalIQQuestions.length === 0 ? (
              <p>No quiz questions are available right now. Check back later.</p>
            ) : (
              <div className="paypal-iq-question-list">
                {paypalIQQuestions.map((question, index) => {
                  const result = paypalIQResults[question.id];
                  const selected = paypalIQSelectedAnswers[question.id] || "";

                  return (
                    <article className="paypal-iq-question" key={question.id}>
                      <div className="paypal-iq-question-meta">
                        <span>QUESTION {index + 1}</span>
                        <span>{question.difficulty}</span>
                      </div>
                      <h3>{question.question}</h3>
                      <p className="paypal-iq-question-context">
                        {question.fact_title} · {question.category}
                      </p>

                      <div className="paypal-iq-options">
                        {question.options.map((option, optionIndex) => {
                          const optionLetter = String.fromCharCode(65 + optionIndex);
                          const isCorrect = result?.correct_option === optionLetter;
                          const isSelected = selected === optionLetter;

                          return (
                            <button
                              type="button"
                              key={optionLetter}
                              className={`paypal-iq-option${isSelected ? " selected" : ""}${result && isCorrect ? " correct" : ""}${result && isSelected && !result.is_correct ? " incorrect" : ""}`}
                              disabled={Boolean(result)}
                              onClick={() =>
                                setPaypalIQSelectedAnswers((current) => ({
                                  ...current,
                                  [question.id]: optionLetter,
                                }))
                              }
                            >
                              <span>{optionLetter}</span>
                              {option}
                            </button>
                          );
                        })}
                      </div>

                      {!result ? (
                        <button
                          type="button"
                          className="paypal-iq-submit"
                          disabled={!selected}
                          onClick={async () => {
                            try {
                              const response = await fetch(
                                apiUrl("/api/paypal-iq/quiz/submit"),
                                {
                                  method: "POST",
                                  headers: {
                                    Authorization: `Bearer ${authToken}`,
                                    "Content-Type": "application/json",
                                  },
                                  body: JSON.stringify({
                                    question_id: question.id,
                                    selected_option: selected,
                                  }),
                                }
                              );

                              const data = await response.json();

                              if (!response.ok) {
                                throw new Error(data.detail || "Could not submit your answer.");
                              }

                              setPaypalIQResults((current) => ({
                                ...current,
                                [question.id]: data as PayPalIQQuizResult,
                              }));

                              if (data.progress) {
                                setPaypalIQProgress(data.progress);
                              }
                            } catch (error) {
                              setPaypalIQError(
                                error instanceof Error
                                  ? error.message
                                  : "Could not submit your answer."
                              );
                            }
                          }}
                        >
                          Submit answer
                        </button>
                      ) : (
                        <div className={`paypal-iq-feedback ${result.is_correct ? "success" : "retry"}`}>
                          <strong>
                            {result.is_correct ? "Correct answer!" : "Not quite. Keep learning!"}
                          </strong>
                          <p>{result.explanation}</p>
                          <span>Points earned: {result.points_awarded}</span>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <section className="panel paypal-iq-library">
            <div className="paypal-iq-section-heading">
              <div>
                <span className="paypal-iq-eyebrow">KNOWLEDGE LIBRARY</span>
                <h2>Explore PayPal facts</h2>
              </div>
              <span>{paypalIQFacts.length} published facts</span>
            </div>

            <div className="paypal-iq-categories">
              <button
                type="button"
                className={paypalIQSelectedCategory === "ALL" ? "active" : ""}
                onClick={() => setPaypalIQSelectedCategory("ALL")}
              >
                All topics
              </button>
              {paypalIQCategories.map((category) => (
                <button
                  type="button"
                  key={category}
                  className={paypalIQSelectedCategory === category ? "active" : ""}
                  onClick={() => setPaypalIQSelectedCategory(category)}
                >
                  {category}
                </button>
              ))}
            </div>

            <div className="paypal-iq-fact-grid">
              {paypalIQFacts
                .filter((fact) =>
                  paypalIQSelectedCategory === "ALL" ||
                  fact.category === paypalIQSelectedCategory
                )
                .map((fact) => (
                  <article className="paypal-iq-library-card" key={fact.id}>
                    <span className="paypal-iq-category">{fact.category}</span>
                    <h3>{fact.title}</h3>
                    <p>{fact.fact_text}</p>
                    {fact.source_url && (
                      <a href={fact.source_url} target="_blank" rel="noreferrer">
                        <ShieldCheck size={14} /> {fact.source_title || "View source"}
                      </a>
                    )}
                  </article>
                ))}
            </div>
          </section>
        </>
      )}
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
              <h1>{new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"}<span className="wave"> {"\u2728"}</span></h1>
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
              <div className="stat-value">
  {dashboard ? dashboard.pending_payments : "--"}
</div>
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
                    <div className="message-content">
                      <div className="message-bubble">{item.text}</div>
                      {item.role === "assistant" && <SemanticDetails semantic={item.semantic} />}
                    </div>
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

          <footer className="page-footer"><span>{"\u00A9"} 2026 PayPilot AI</span><span><ShieldCheck size={13} /> Built with security in mind</span><span><Zap size={13} /> Powered by intelligent workflows</span></footer>
        </div>
        </div>
      </main>
    </div>
  );
}

export default App;














