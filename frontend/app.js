const API_BASE_URL = 'http://localhost:8000';
let priceChart = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initial fetch
    fetchData('SBIN', 'NSE');
    fetchBulkDeals();

    // Event listener for search
    document.getElementById('searchBtn').addEventListener('click', () => {
        const symbol = document.getElementById('tickerSearch').value.trim().toUpperCase();
        const exchange = document.querySelector('input[name="exchange"]:checked').value;
        if (symbol) {
            fetchData(symbol, exchange);
        }
    });

    // Handle range filters
    document.getElementById('range1M').addEventListener('click', (e) => setRangeActive(e, 30));
    document.getElementById('range3M').addEventListener('click', (e) => setRangeActive(e, 90));
    document.getElementById('range6M').addEventListener('click', (e) => setRangeActive(e, 180));
});

function setRangeActive(event, days) {
    document.querySelectorAll('.flex button').forEach(b => {
        if (b.id && b.id.startsWith('range')) {
            b.classList.replace('bg-[#2196F3]', 'text-neutral-400');
            b.classList.add('hover:text-white');
        }
    });
    event.target.classList.replace('text-neutral-400', 'bg-[#2196F3]');
    event.target.classList.remove('hover:text-white');
    event.target.classList.add('text-white');
    
    const symbol = document.getElementById('tickerSearch').value.trim().toUpperCase();
    const exchange = document.querySelector('input[name="exchange"]:checked').value;
    fetchHistorical(symbol, exchange, days);
}

// Fetch all stock data
async function fetchData(symbol, exchange) {
    showLoading();
    try {
        await Promise.all([
            fetchQuote(symbol, exchange),
            fetchProfile(symbol, exchange),
            fetchHistorical(symbol, exchange, 30),
            fetchNews(symbol, exchange)
        ]);
    } catch (error) {
        console.error("Error loading stock data:", error);
    }
}

// 1. Fetch Quote
async function fetchQuote(symbol, exchange) {
    try {
        const res = await fetch(`${API_BASE_URL}/equity/quote?symbol=${symbol}&exchange=${exchange}`);
        if (!res.ok) throw new Error("Failed to fetch quote");
        const data = await res.json();
        
        const changeColor = data.change >= 0 ? 'text-emerald-400' : 'text-rose-500';
        const changeIcon = data.change >= 0 ? 'fa-arrow-up' : 'fa-arrow-down';
        
        document.getElementById('quoteCards').innerHTML = `
            <div class="col-span-2 bg-[#121212] border border-neutral-700 p-3 rounded-lg text-center">
                <div class="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider mb-1">Price</div>
                <div class="text-xl font-bold text-white">${data.price.toFixed(2)}</div>
                <div class="text-[11px] ${changeColor} flex items-center justify-center gap-1 mt-0.5 font-semibold">
                    <i class="fa-solid ${changeIcon}"></i> ${data.change.toFixed(2)} (${data.change_pct.toFixed(2)}%)
                </div>
            </div>
            <div class="col-span-2 bg-[#121212] border border-neutral-700 p-3 rounded-lg text-center">
                <div class="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider mb-1">Day High / Low</div>
                <div class="text-xs font-bold text-white py-1">${data.high.toFixed(2)} / ${data.low.toFixed(2)}</div>
            </div>
            <div class="col-span-2 bg-[#121212] border border-neutral-700 p-3 rounded-lg text-center">
                <div class="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider mb-1">Prev Close</div>
                <div class="text-sm font-bold text-neutral-200 py-1">${data.prev_close.toFixed(2)}</div>
            </div>
            <div class="col-span-2 bg-[#121212] border border-neutral-700 p-3 rounded-lg text-center">
                <div class="text-[10px] text-neutral-400 font-semibold uppercase tracking-wider mb-1">Volume</div>
                <div class="text-sm font-bold text-neutral-200 py-1">${data.volume.toLocaleString()}</div>
            </div>
        `;
    } catch (err) {
        document.getElementById('quoteCards').innerHTML = `
            <div class="col-span-2 bg-rose-500/10 text-rose-400 border border-rose-500/20 p-4 rounded-xl text-center text-xs">
                Error quote
            </div>
        `;
    }
}

// 2. Fetch Profile
async function fetchProfile(symbol, exchange) {
    try {
        const res = await fetch(`${API_BASE_URL}/equity/profile?symbol=${symbol}&exchange=${exchange}`);
        if (!res.ok) throw new Error("Failed to fetch profile");
        const data = await res.json();
        
        document.getElementById('profileContent').innerHTML = `
            <div class="flex-1 flex flex-col gap-4">
                <div>
                    <h4 class="text-md font-bold text-white tracking-tight">${data.name || symbol}</h4>
                    <p class="text-xs text-neutral-400">${data.exchange} Exchange (${data.currency})</p>
                </div>
                <div class="grid grid-cols-2 gap-2 text-xs border-y border-neutral-700 py-3">
                    <div><span class="text-neutral-500 block mb-0.5">Sector</span><span class="font-medium text-neutral-200">${data.sector || 'N/A'}</span></div>
                    <div><span class="text-neutral-500 block mb-0.5">Industry</span><span class="font-medium text-neutral-200">${data.industry || 'N/A'}</span></div>
                </div>
                <p class="text-xs text-neutral-400 leading-relaxed overflow-y-auto max-h-[140px] custom-scrollbar pr-1">
                    ${data.description || 'No business summary available.'}
                </p>
                ${data.website ? `<a href="${data.website}" target="_blank" class="text-xs text-[#2196F3] hover:underline mt-auto self-start"><i class="fa-solid fa-link mr-1"></i> Official Website</a>` : ''}
            </div>
        `;
    } catch (err) {
        document.getElementById('profileContent').innerHTML = `
            <div class="text-center text-neutral-500 py-6 text-sm">No profile data available for ${symbol}</div>
        `;
    }
}

// 3. Fetch Historical & Plot Chart
async function fetchHistorical(symbol, exchange, days = 30) {
    const startTime = performance.now();
    try {
        const endDate = new Date();
        const startDate = new Date();
        startDate.setDate(endDate.getDate() - days);
        
        const startStr = startDate.toISOString().split('T')[0];
        const endStr = endDate.toISOString().split('T')[0];
        
        const res = await fetch(`${API_BASE_URL}/equity/historical?symbol=${symbol}&exchange=${exchange}&start_date=${startStr}&end_date=${endStr}`);
        if (!res.ok) throw new Error("Failed to fetch historical prices");
        const data = await res.json();
        
        // Calculate query response latency
        const endTime = performance.now();
        const latency = Math.round(endTime - startTime);
        
        document.getElementById('latencyStat').innerText = `${latency} ms`;
        document.getElementById('recordsCount').innerText = data.length;
        
        // Render chart
        renderChart(data);
    } catch (err) {
        console.error(err);
    }
}

// Render Line Chart
function renderChart(data) {
    const dates = data.map(d => d.date);
    const prices = data.map(d => d.close);
    
    if (priceChart) {
        priceChart.destroy();
    }
    
    const ctx = document.getElementById('priceChart').getContext('2d');
    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [{
                label: 'Close Price',
                data: prices,
                borderColor: '#2196F3',
                borderWidth: 2.5,
                pointRadius: 0,
                pointHoverRadius: 5,
                fill: true,
                backgroundColor: (context) => {
                    const ctx = context.chart.ctx;
                    const gradient = ctx.createLinearGradient(0, 0, 0, 320);
                    gradient.addColorStop(0, 'rgba(33, 150, 243, 0.18)');
                    gradient.addColorStop(1, 'rgba(33, 150, 243, 0.0)');
                    return gradient;
                },
                tension: 0.15
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { color: '#8e8e8e', font: { size: 10 } }
                },
                y: {
                    grid: { color: '#2d2d2d' },
                    ticks: { color: '#8e8e8e', font: { size: 10 } }
                }
            }
        }
    });
}

// 4. Fetch News
async function fetchNews(symbol, exchange) {
    try {
        const res = await fetch(`${API_BASE_URL}/equity/news?symbol=${symbol}&exchange=${exchange}`);
        if (!res.ok) throw new Error("Failed to fetch news");
        const news = await res.json();
        
        if (news.length === 0) {
            document.getElementById('newsContent').innerHTML = `<div class="text-center text-neutral-500 py-6 text-sm">No news found for ${symbol}</div>`;
            return;
        }
        
        document.getElementById('newsContent').innerHTML = news.map(item => `
            <a href="${item.link}" target="_blank" class="block bg-[#121212] hover:bg-[#1e1e1e] border border-neutral-700 p-3 rounded transition">
                <h5 class="text-xs font-semibold text-white leading-snug mb-1">${item.title}</h5>
                <div class="flex justify-between text-[10px] text-neutral-500">
                    <span>${item.publisher}</span>
                    <span>${new Date(item.providerPublishTime * 1000).toLocaleDateString()}</span>
                </div>
            </a>
        `).join('');
    } catch (err) {
        document.getElementById('newsContent').innerHTML = `<div class="text-center text-neutral-500 py-6 text-sm">Error loading news feed.</div>`;
    }
}

// 5. Fetch Institutional Bulk Deals
async function fetchBulkDeals() {
    try {
        const res = await fetch(`${API_BASE_URL}/api/institutional/latest-bulk-deals`);
        if (!res.ok) throw new Error("Failed to fetch deals");
        const data = await res.json();
        
        document.getElementById('bulkDealsContent').innerHTML = `
            <table class="w-full text-left text-xs border-collapse">
                <thead>
                    <tr class="border-b border-neutral-700 text-neutral-500 font-medium">
                        <th class="py-2.5">Date</th>
                        <th class="py-2.5">Symbol</th>
                        <th class="py-2.5">Client Name</th>
                        <th class="py-2.5 text-center">Type</th>
                        <th class="py-2.5 text-right">Quantity</th>
                        <th class="py-2.5 text-right">Price</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-neutral-800 text-neutral-300">
                    ${data.map(deal => `
                        <tr>
                            <td class="py-2.5">${deal.trade_date}</td>
                            <td class="py-2.5 font-bold text-white">${deal.symbol}</td>
                            <td class="py-2.5 font-medium max-w-[120px] truncate" title="${deal.client_name}">${deal.client_name}</td>
                            <td class="py-2.5 text-center">
                                <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${deal.deal_type === 'BUY' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}">${deal.deal_type}</span>
                            </td>
                            <td class="py-2.5 text-right">${deal.quantity.toLocaleString()}</td>
                            <td class="py-2.5 text-right font-medium text-white">${deal.price.toFixed(2)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (err) {
        document.getElementById('bulkDealsContent').innerHTML = `<div class="text-center text-neutral-500 py-6 text-sm">No transaction logs available.</div>`;
    }
}

// Show placeholder state while loading
function showLoading() {
    document.getElementById('profileContent').innerHTML = `
        <div class="flex-1 flex flex-col justify-center items-center gap-2 py-12">
            <span class="animate-spin h-5 w-5 border-2 border-[#2196F3] border-t-transparent rounded-full"></span>
            <span class="text-xs text-neutral-500 font-medium">Querying local databases...</span>
        </div>
    `;
}
