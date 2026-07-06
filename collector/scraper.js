// scraper.js
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs').promises;
const https = require('https');
const crypto = require('crypto');
const { parseJerseyNumber } = require('./playerNameUtils');

// Post-process a scraped box score payload to add a structured jerseyNumber
// field to each hitting/pitching entry (parsed from the existing Info string),
// plus a per-team rosterByNumber map so downstream code can resolve "#25" or
// ambiguous names back to a canonical player within the game.
function enrichBoxScoreWithJerseyNumbers(boxScoreData) {
    if (!boxScoreData) return boxScoreData;
    const rosterByNumber = {};
    ['hitting', 'pitching'].forEach(section => {
        if (!Array.isArray(boxScoreData[section])) return;
        boxScoreData[section].forEach(entry => {
            if (!entry) return;
            entry.jerseyNumber = parseJerseyNumber(entry.Info);
            const team = entry.teamName;
            if (team && entry.jerseyNumber) {
                if (!rosterByNumber[team]) rosterByNumber[team] = {};
                // Prefer the most complete (longest) name seen for this team+number.
                const existing = rosterByNumber[team][entry.jerseyNumber];
                const candidate = entry.Player || '';
                if (!existing || candidate.length > existing.length) {
                    rosterByNumber[team][entry.jerseyNumber] = candidate;
                }
            }
        });
    });
    boxScoreData.rosterByNumber = rosterByNumber;
    return boxScoreData;
}

// Helper to fetch image and convert to base64
function fetchImageAsBase64(url) {
    return new Promise((resolve, reject) => {
        if (!url || !(url.startsWith('http:') || url.startsWith('https:'))) {
            return resolve(null);
        }

        const protocol = url.startsWith('https:') ? https : require('http');

        protocol.get(url, (response) => {
            // Follow redirects
            if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
                return fetchImageAsBase64(response.headers.location).then(resolve).catch(reject);
            }
            if (response.statusCode !== 200) {
                return reject(new Error(`Failed to get image, status code: ${response.statusCode}`));
            }
            const data = [];
            response.on('data', (chunk) => {
                data.push(chunk);
            });
            response.on('end', () => {
                const buffer = Buffer.concat(data);
                const base64 = buffer.toString('base64');
                const contentType = response.headers['content-type'] || 'image/jpeg';
                resolve(`data:${contentType};base64,${base64}`);
            });
        }).on('error', reject);
    });
}

// Test mode configuration - allows testing without hitting real GameChanger
const TEST_MODE = process.env.TEST_MODE === 'true';
const MOCK_DATA = TEST_MODE ? require('./__tests__/fixtures/mockGameData') : null;

const PUPPETEER_BASE_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-accelerated-2d-canvas',
    '--no-first-run',
    '--no-zygote',
    '--disable-gpu'
];

const SCRAPER_MAX_BROWSER_RECOVERY_FAILURES = 2;

const GAME_ERROR_TYPES = {
    NO_DATA: 'NO_DATA',
    INFRA_BROWSER: 'INFRA_BROWSER',
    PREMIUM_ACCESS_REQUIRED: 'PREMIUM_ACCESS_REQUIRED',
    OTHER_GAME_ERROR: 'OTHER_GAME_ERROR'
};

const GAMECHANGER_AUTH_ORIGINS = [
    'https://web.gc.com',
    'https://gc.com',
    'https://api.gc.com'
];

function getUserRootDataPath(userId) {
    return path.join(__dirname, 'user_data', String(userId || '').trim());
}

function getUserDataPath(userId, credentialFingerprint = null) {
    const rootPath = getUserRootDataPath(userId);

    if (!credentialFingerprint) {
        return rootPath;
    }

    const fingerprintSegment = String(credentialFingerprint).trim().slice(0, 16) || 'default';
    return path.join(rootPath, `cred_${fingerprintSegment}`);
}

function isGameChangerDomain(rawDomain = '') {
    const domain = String(rawDomain || '').trim().replace(/^\./, '').toLowerCase();
    return domain === 'gc.com' || domain.endsWith('.gc.com');
}

function buildOriginCandidatesFromCookies(cookies = []) {
    const origins = new Set();

    for (const cookie of cookies) {
        const rawDomain = cookie?.domain;
        if (!rawDomain || !isGameChangerDomain(rawDomain)) continue;

        const domain = String(rawDomain).replace(/^\./, '').toLowerCase();
        origins.add(`https://${domain}`);

        // Some auth flows bounce through www.
        if (!domain.startsWith('www.')) {
            origins.add(`https://www.${domain}`);
        }
    }

    return origins;
}

function buildOriginCandidatesFromPages(pages = []) {
    const origins = new Set();

    for (const currentPage of pages) {
        const pageUrl = currentPage?.url?.();
        if (!pageUrl || !pageUrl.startsWith('http')) continue;

        try {
            const parsed = new URL(pageUrl);
            if (isGameChangerDomain(parsed.hostname)) {
                origins.add(parsed.origin);
            }
        } catch (_) {
            // Ignore malformed URLs during cleanup.
        }
    }

    return origins;
}

function summarizeCookieDomains(cookies = []) {
    const domainCounts = new Map();

    for (const cookie of cookies) {
        const domain = String(cookie?.domain || '').replace(/^\./, '').toLowerCase();
        if (!domain) continue;
        domainCounts.set(domain, (domainCounts.get(domain) || 0) + 1);
    }

    return Array.from(domainCounts.entries())
        .sort((a, b) => b[1] - a[1])
        .map(([domain, count]) => `${domain}:${count}`);
}

async function clearPageStorageArtifacts(targetPage) {
    if (!targetPage || (typeof targetPage.isClosed === 'function' && targetPage.isClosed())) {
        return;
    }

    await targetPage.evaluate(async () => {
        try { localStorage.clear(); } catch (_) {}
        try { sessionStorage.clear(); } catch (_) {}

        try {
            if (window.indexedDB && typeof indexedDB.databases === 'function') {
                const databases = await indexedDB.databases();
                await Promise.all((databases || []).map(db => {
                    if (!db?.name) return Promise.resolve();
                    return new Promise(resolve => {
                        const request = indexedDB.deleteDatabase(db.name);
                        request.onsuccess = request.onerror = request.onblocked = () => resolve();
                    });
                }));
            }
        } catch (_) {}

        try {
            if (window.caches && typeof caches.keys === 'function') {
                const cacheNames = await caches.keys();
                await Promise.all(cacheNames.map(name => caches.delete(name).catch(() => false)));
            }
        } catch (_) {}

        try {
            if (navigator?.serviceWorker?.getRegistrations) {
                const registrations = await navigator.serviceWorker.getRegistrations();
                await Promise.all((registrations || []).map(reg => reg.unregister().catch(() => false)));
            }
        } catch (_) {}
    }).catch(() => {});
}

async function clearInMemoryAuthState(browser, page = null, { userId = null } = {}) {
    if (!browser || !isBrowserConnected(browser)) {
        return;
    }

    let createdTempPage = null;
    let createdHelperPage = null;
    let cdpClient = null;

    try {
        const pageSet = new Set();
        const contexts = typeof browser.browserContexts === 'function' ? browser.browserContexts() : [];

        for (const context of contexts) {
            const contextPages = await context.pages().catch(() => []);
            for (const contextPage of contextPages) {
                if (contextPage && !(typeof contextPage.isClosed === 'function' && contextPage.isClosed())) {
                    pageSet.add(contextPage);
                }
            }
        }

        if (page && !(typeof page.isClosed === 'function' && page.isClosed())) {
            pageSet.add(page);
        }

        if (pageSet.size === 0) {
            createdTempPage = await browser.newPage();
            pageSet.add(createdTempPage);
        }

        const pages = Array.from(pageSet);
        const primaryPage = pages[0];
        if (!primaryPage) {
            return;
        }

        cdpClient = await primaryPage.target().createCDPSession();
        await cdpClient.send('Network.enable').catch(() => {});

        const allCookiesBefore = (await cdpClient.send('Network.getAllCookies').catch(() => ({ cookies: [] }))).cookies || [];
        const gameChangerCookiesBefore = allCookiesBefore.filter(cookie => isGameChangerDomain(cookie?.domain));

        const originCandidates = new Set([
            ...GAMECHANGER_AUTH_ORIGINS,
            ...buildOriginCandidatesFromCookies(gameChangerCookiesBefore),
            ...buildOriginCandidatesFromPages(pages),
            'https://auth.gc.com',
            'https://accounts.gc.com'
        ]);

        const beforeSummary = summarizeCookieDomains(gameChangerCookiesBefore).slice(0, 10).join(', ');
        console.log(`[SCRAPER][AUTH_RESET] Pre-clear cookie snapshot for user ${userId || 'unknown'}: total=${allCookiesBefore.length}, gc=${gameChangerCookiesBefore.length}${beforeSummary ? ` [${beforeSummary}]` : ''}`);

        await cdpClient.send('Network.clearBrowserCookies').catch(() => {});
        await cdpClient.send('Network.clearBrowserCache').catch(() => {});

        for (const origin of originCandidates) {
            await cdpClient.send('Storage.clearDataForOrigin', {
                origin,
                storageTypes: 'all'
            }).catch(() => {});
        }

        for (const activePage of pages) {
            await clearPageStorageArtifacts(activePage);
        }

        const helperPage = createdTempPage || await browser.newPage();
        if (!createdTempPage) {
            createdHelperPage = helperPage;
        }

        for (const origin of originCandidates) {
            try {
                await helperPage.goto(origin, { waitUntil: 'domcontentloaded', timeout: 10000 });
                await clearPageStorageArtifacts(helperPage);
            } catch (_) {
                // Best effort: some origins may fail to load but should still be covered by CDP clearing.
            }
        }

        const allCookiesAfter = (await cdpClient.send('Network.getAllCookies').catch(() => ({ cookies: [] }))).cookies || [];
        let gameChangerCookiesAfter = allCookiesAfter.filter(cookie => isGameChangerDomain(cookie?.domain));

        if (gameChangerCookiesAfter.length > 0) {
            for (const cookie of gameChangerCookiesAfter) {
                await cdpClient.send('Network.deleteCookies', {
                    name: cookie.name,
                    domain: cookie.domain,
                    path: cookie.path || '/'
                }).catch(() => {});
            }

            const cookieStateAfterDelete = (await cdpClient.send('Network.getAllCookies').catch(() => ({ cookies: [] }))).cookies || [];
            gameChangerCookiesAfter = cookieStateAfterDelete.filter(cookie => isGameChangerDomain(cookie?.domain));
        }

        const afterSummary = summarizeCookieDomains(gameChangerCookiesAfter).slice(0, 10).join(', ');
        console.log(`[SCRAPER][AUTH_RESET] Post-clear cookie snapshot for user ${userId || 'unknown'}: total=${allCookiesAfter.length}, gc=${gameChangerCookiesAfter.length}${afterSummary ? ` [${afterSummary}]` : ''}`);

        if (gameChangerCookiesAfter.length > 0) {
            const survivors = gameChangerCookiesAfter
                .slice(0, 8)
                .map(cookie => `${cookie.name}@${String(cookie.domain || '').replace(/^\./, '')}${cookie.path || '/'}`)
                .join(', ');
            console.warn(`[SCRAPER][AUTH_RESET] Residual GameChanger cookies after reset for user ${userId || 'unknown'}: ${survivors}`);
        }

        if (userId) {
            console.log(`[SCRAPER][AUTH_RESET] Cleared in-memory browser auth state for user ${userId}. Origins attempted=${originCandidates.size}.`);
        }
    } finally {
        if (cdpClient) {
            await cdpClient.detach().catch(() => {});
        }

        if (createdHelperPage) {
            await closePageSafely(createdHelperPage);
        }

        if (createdTempPage) {
            await closePageSafely(createdTempPage);
        }
    }
}

async function clearPersistedAuthState(userId) {
    if (!userId) {
        return;
    }

    const userDataRootPath = getUserRootDataPath(userId);

    try {
        await fs.rm(userDataRootPath, { recursive: true, force: true });
        const rootStillExists = await fs.access(userDataRootPath).then(() => true).catch(() => false);
        console.log(`[SCRAPER][AUTH_RESET] Removed user profile root ${userDataRootPath}. existsAfter=${rootStillExists}`);
    } catch (error) {
        console.warn(`[SCRAPER][AUTH_RESET] Failed to remove user profile path ${userDataRootPath}: ${error.message}`);
    }

    // Legacy token cache path used by API tooling; clear so stale tokens cannot bleed between accounts.
    const legacyTokenFile = path.join(__dirname, 'reports', 'gc-token.json');
    try {
        await fs.rm(legacyTokenFile, { force: true });
    } catch (error) {
        console.warn(`[SCRAPER][AUTH_RESET] Failed to remove legacy token cache ${legacyTokenFile}: ${error.message}`);
    }
}

async function resetGameChangerSessionState(userId, { browser = null, page = null } = {}) {
    if (!TEST_MODE) {
        await clearInMemoryAuthState(browser, page, { userId }).catch((error) => {
            console.warn(`[SCRAPER][AUTH_RESET] Browser state reset warning for user ${userId}: ${error.message}`);
        });
    }

    await clearPersistedAuthState(userId);

    if (userId) {
        console.log(`[SCRAPER][AUTH_RESET] Cleared persisted GameChanger auth state for user ${userId}.`);
    }
}

function buildBrowserLaunchOptions({ userDataDir } = {}) {
    const launchOptions = {
        headless: true,
        args: [...PUPPETEER_BASE_ARGS]
    };

    if (userDataDir) {
        launchOptions.userDataDir = userDataDir;
    }

    return launchOptions;
}

function attachBrowserSessionMeta(browser, meta = {}) {
    if (!browser) return;
    browser.__scoutSessionMeta = {
        ...(browser.__scoutSessionMeta || {}),
        ...meta
    };
}

function getBrowserSessionMeta(browser, page) {
    return browser?.__scoutSessionMeta || page?.__scoutSessionMeta || null;
}

function isBrowserConnected(browser) {
    return Boolean(browser && typeof browser.isConnected === 'function' && browser.isConnected());
}

function isBrowserInfraError(error, browser, page) {
    const rawMessage = `${error?.message || ''} ${error?.stack || ''}`;
    const message = rawMessage.toLowerCase();

    if (!isBrowserConnected(browser)) return true;
    if (page && typeof page.isClosed === 'function' && page.isClosed()) return true;

    const infraIndicators = [
        'target closed',
        'target.createtarget',
        'connection closed',
        'browser has disconnected',
        'session closed',
        'protocol error',
        'navigation failed because browser has disconnected',
        'cannot find context with specified id'
    ];

    return infraIndicators.some(indicator => message.includes(indicator));
}

function isNoDataError(error) {
    const rawMessage = `${error?.message || ''} ${error?.stack || ''}`;
    const message = rawMessage.toLowerCase();

    const timedOutOnExpectedSelector =
        message.includes('waiting for selector') && (
            message.includes('boxscorecomponents__playername') ||
            message.includes('batsplays__play')
        );

    return timedOutOnExpectedSelector;
}

function classifyGameError(error, browser, page) {
    if (error?.message === 'PREMIUM_ACCESS_REQUIRED') {
        return GAME_ERROR_TYPES.PREMIUM_ACCESS_REQUIRED;
    }

    if (isBrowserInfraError(error, browser, page)) {
        return GAME_ERROR_TYPES.INFRA_BROWSER;
    }

    if (isNoDataError(error)) {
        return GAME_ERROR_TYPES.NO_DATA;
    }

    return GAME_ERROR_TYPES.OTHER_GAME_ERROR;
}

function buildCredentialFingerprint(gcEmail, gcPassword) {
    return crypto
        .createHash('sha256')
        .update(`${gcEmail || ''}\u0000${gcPassword || ''}`)
        .digest('hex');
}

async function closePageSafely(targetPage) {
    if (!targetPage) return;
    try {
        if (!targetPage.isClosed()) {
            await targetPage.close();
        }
    } catch (_) {
        // ignore best-effort cleanup errors
    }
}

async function closeBrowserSafely(targetBrowser) {
    if (!targetBrowser) return;
    try {
        if (isBrowserConnected(targetBrowser)) {
            await targetBrowser.close();
        }
    } catch (_) {
        // ignore best-effort cleanup errors
    }
}

async function detectPaywall(page, options = {}) {
    if (!page) return false;

    const { requireBlurredCells = false } = options;

    try {
        const paywallState = await page.evaluate(() => {
            const hasPaywallContainer = Boolean(document.querySelector('.BoxScore__paywallContainer'));
            const hasPaywallTestId = Boolean(document.querySelector('[data-testid="paywall"]'));
            const blurredCells = document.querySelectorAll('.BoxScore__blurred');
            const blurredPlayerCells = document.querySelectorAll('.BoxScoreComponents__playerCell.BoxScore__blurred');
            const pageText = (document.body?.innerText || '').toLowerCase();
            const hasPaywallText = [
                'try premium for free',
                'subscribe to unlock',
                'upgrade to premium',
                'premium subscription'
            ].some(text => pageText.includes(text));

            return {
                hasPaywallContainer,
                hasPaywallTestId,
                hasBlurredCells: blurredCells.length > 0,
                blurredCellCount: blurredCells.length,
                blurredPlayerCellCount: blurredPlayerCells.length,
                hasPaywallText
            };
        });

        const hasBannerSignal = paywallState.hasPaywallContainer || paywallState.hasPaywallTestId || paywallState.hasPaywallText;
        const hasBlurSignal = paywallState.hasBlurredCells || paywallState.blurredPlayerCellCount > 0;

        return requireBlurredCells
            ? hasBlurSignal
            : hasBannerSignal || hasBlurSignal;
    } catch (error) {
        console.warn(`[SCRAPER][PAYWALL_CHECK] Failed to evaluate paywall state: ${error.message}`);
        return false;
    }
}

// --- PURE JAVASCRIPT SCRAPING FUNCTIONS ---
function scrapePlaysFromPage() {
    const strictRows = document.querySelectorAll('div.BatsPlays__play:has(div.BatsPlays__smallPlayHeader)');
    const rows = strictRows.length > 0
        ? strictRows
        : document.querySelectorAll('div.BatsPlays__play');

    const allPlaysData = [];

    rows.forEach(row => {
        const playDetails = row.querySelectorAll('div.BatsPlays__playDetails, [class*="playDetails"]');

        if (playDetails.length >= 2) {
            allPlaysData.push({
                pitch: playDetails[0].innerText.trim(),
                play: playDetails[1].innerText.trim()
            });
            return;
        }

        if (playDetails.length === 1) {
            const singleDetailText = playDetails[0].innerText.trim();
            if (singleDetailText) {
                allPlaysData.push({ pitch: '', play: singleDetailText });
            }
            return;
        }

        const lines = (row.innerText || '')
            .split('\n')
            .map(line => line.trim())
            .filter(Boolean);

        if (lines.length >= 2) {
            allPlaysData.push({
                pitch: lines[lines.length - 2],
                play: lines[lines.length - 1]
            });
        }
    });

    return allPlaysData.filter(play => (play.pitch || play.play));
}

function buildExtraStatsGameNoteKey(teamPrefix, sectionType, label) {
    if (!teamPrefix || !label) return '';
    return sectionType === 'pitching' ? `${teamPrefix}Pitching ${label}` : `${teamPrefix}${label}`;
}

function scrapeBoxScoreFromPage() {
    function buildExtraStatsGameNoteKey(teamPrefix, sectionType, label) {
        if (!teamPrefix || !label) return '';
        return sectionType === 'pitching' ? `${teamPrefix}Pitching ${label}` : `${teamPrefix}${label}`;
    }

    const allTablesData = { 
        hitting: [], 
        pitching: [],
        gameNotes: {},
        awayTeamName: document.querySelector('.BoxScore__awayTeamName')?.innerText.trim() || 'Away',
        homeTeamName: document.querySelector('.BoxScore__homeTeamName')?.innerText.trim() || 'Home'
    };
    
    const allDataTables = document.querySelectorAll('[data-testid="data-table"]');
    allDataTables.forEach(tableElement => {
        const headerElement = tableElement.querySelector('.ag-header-cell-text');
        if (!headerElement) return;

        const headerText = headerElement.innerText.trim().toUpperCase();
        const currentSection = headerText.includes('PITCHING') ? 'pitching' : 'hitting';

        let currentTeamName = '';
        const parentContainer = tableElement.parentElement;
        if (parentContainer) {
            if (parentContainer.classList.contains('BoxScore__awayLineup') || parentContainer.classList.contains('BoxScore__awayPitching')) {
                currentTeamName = allTablesData.awayTeamName;
            } else if (parentContainer.classList.contains('BoxScore__homeLineup') || parentContainer.classList.contains('BoxScore__homePitching')) {
                currentTeamName = allTablesData.homeTeamName;
            }
        }

        const headers = Array.from(tableElement.querySelectorAll('.ag-header-row .ag-header-cell-text')).map(h => h.innerText.trim());
        headers[0] = 'Player';

        const dataRows = tableElement.querySelectorAll('.ag-center-cols-container .ag-row');
        dataRows.forEach(row => {
            const stats = {};
            const cells = row.querySelectorAll('[role="gridcell"]');
            if (cells.length === 0) return;

            const playerName = cells[0].querySelector('.BoxScoreComponents__playerName')?.innerText.trim();
            if (!playerName || playerName === 'TEAM') return;

            stats['teamName'] = currentTeamName;
            stats['Player'] = playerName.replace(/\s*\((?:RS[\s-]*|R-)?(?:Fr|So|Jr|Sr|Gr|5th)\)\s*$/i, '').trim();
            stats['Info'] = cells[0].querySelector('.BoxScoreComponents__playerInfo')?.innerText.trim() || '';

            for (let i = 1; i < headers.length; i++) {
                if (headers[i] && cells[i]) {
                    stats[headers[i]] = cells[i].innerText.trim();
                }
            }
            allTablesData[currentSection].push(stats);
        });
    });

    const extraStatsSections = document.querySelectorAll('.BoxScoreComponents__boxScoreExtraStats');
    extraStatsSections.forEach(section => {
        let teamPrefix = '';
        let sectionType = 'lineup';

        if (section.classList.contains('BoxScore__awayLineupExtra')) {
            teamPrefix = 'Away ';
            sectionType = 'lineup';
        } else if (section.classList.contains('BoxScore__homeLineupExtra')) {
            teamPrefix = 'Home ';
            sectionType = 'lineup';
        } else if (section.classList.contains('BoxScore__awayPitchingExtra')) {
            teamPrefix = 'Away ';
            sectionType = 'pitching';
        } else if (section.classList.contains('BoxScore__homePitchingExtra')) {
            teamPrefix = 'Home ';
            sectionType = 'pitching';
        }

        const lines = section.querySelectorAll(':scope > div');
        lines.forEach(line => {
            const labelEl = line.querySelector('span.Text__semibold');
            if (labelEl) {
                const label = labelEl.innerText.replace(':', '').trim();
                const yearSuffixRe = /\s*\((?:RS[\s-]*|R-)?(?:Fr|So|Jr|Sr|Gr|5th)\)\s*/gi;
                const values = Array.from(line.querySelectorAll('span.BoxScoreComponents__extraPlayerStat')).map(span => span.innerText.trim().replace(yearSuffixRe, ' ').trim());
                const uniqueKey = buildExtraStatsGameNoteKey(teamPrefix, sectionType, label);
                if (!uniqueKey) return;
                if (allTablesData.gameNotes[uniqueKey]) {
                    allTablesData.gameNotes[uniqueKey] += `, ${values.join(' ')}`;
                } else {
                    allTablesData.gameNotes[uniqueKey] = values.join(' ');
                }
            }
        });
    });
    return allTablesData;
}

// Helper to setup interception on any page instance
async function setupGamePageInterception(page) {
    await page.setRequestInterception(true);
    page.on('request', (req) => {
        if (['image', 'stylesheet', 'font'].includes(req.resourceType())) {
            req.abort();
        } else {
            req.continue();
        }
    });
}

function normalizeGameUrl(url) {
    if (!url || typeof url !== 'string') return null;
    return url.trim().replace(/\/$/, '').split('?')[0];
}

function normalizeDateForOutput(rawDate) {
    if (!rawDate || typeof rawDate !== 'string') return 'Unknown Date';

    const trimmed = rawDate.trim();
    if (!trimmed) return 'Unknown Date';

    // Already in M/D format
    if (/^\d{1,2}\/\d{1,2}$/.test(trimmed)) {
        return trimmed;
    }

    // Convert ISO-style date to M/D
    const isoMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
        return `${parseInt(isoMatch[2], 10)}/${parseInt(isoMatch[3], 10)}`;
    }

    // Try generic date parsing as fallback
    const parsed = new Date(trimmed);
    if (!Number.isNaN(parsed.getTime()) && parsed.getFullYear() > 2000) {
        return `${parsed.getMonth() + 1}/${parsed.getDate()}`;
    }

    return trimmed;
}

async function extractGamesMetadata(scheduleUrl) {
    if (!scheduleUrl || typeof scheduleUrl !== 'string') {
        throw new Error('A valid schedule URL is required.');
    }

    // TEST MODE: Return predictable metadata from fixture data
    if (TEST_MODE) {
        const mockGames = (MOCK_DATA?.mockGamesData || []).map((game, index) => ({
            id: `game-${index + 1}`,
            opponent: game.boxScore?.homeTeamName || game.boxScore?.awayTeamName || 'Unknown Opponent',
            result: index % 2 === 0 ? 'W' : 'L',
            date: `1/${Math.min(index + 1, 31)}`,
            score: '5-3',
            gameUrl: normalizeGameUrl(game.gameUrl),
            isCompleted: true
        }));

        return mockGames;
    }

    let browser;
    let page;

    try {
        browser = await puppeteer.launch(buildBrowserLaunchOptions());

        page = await browser.newPage();
        await page.setViewport({ width: 1280, height: 800 });
        await setupGamePageInterception(page);

        await page.goto(scheduleUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await page.waitForSelector('div.ScheduleSection__section', { timeout: 30000 });

        // Get current year as fallback when header year is missing
        const currentYear = new Date().getFullYear();

        // Grab the team name from the schedule page header so callers (e.g.,
        // multi-source preview) can surface the URL-owning team to the user.
        const ownerTeamName = await page.evaluate(() => {
            const normalize = (value) => (value || '').replace(/\s+/g, ' ').trim();
            const badValues = new Set(['schedule', 'team schedule', 'games', 'home']);

            const isUsefulName = (value) => {
                const normalized = normalize(value).toLowerCase();
                if (!normalized) return false;
                if (badValues.has(normalized)) return false;
                if (normalized.length < 4) return false;
                return /[a-z]/i.test(normalized);
            };

            const selectors = [
                '[class*="NewTeamNavBar"] [class*="teamName"]',
                '[class*="NewTeamNavBar"] [class*="TeamName"]',
                'span.NewTeamNavBar__teamName',
                '[class*="TeamProfileHeader"] h1',
                '[class*="TeamHeader"] h1',
                'header h1',
                'h1'
            ];

            for (const sel of selectors) {
                const el = document.querySelector(sel);
                const text = normalize(el?.textContent || '');
                if (isUsefulName(text)) return text;
            }

            const metaCandidates = [
                document.querySelector('meta[property="og:title"]')?.getAttribute('content'),
                document.querySelector('meta[name="twitter:title"]')?.getAttribute('content'),
                document.title
            ];

            for (const candidate of metaCandidates) {
                const text = normalize(String(candidate || '').replace(/\s*[|\-–].*$/, ''));
                if (isUsefulName(text)) return text;
            }

            return '';
        }).catch(() => '');

        const games = await page.evaluate((year) => {
            const normalizeText = (value) => (value || '').replace(/\s+/g, ' ').trim();
            const monthNames = [
                'january', 'february', 'march', 'april', 'may', 'june',
                'july', 'august', 'september', 'october', 'november', 'december'
            ];

            const parseMonthHeader = (headerText) => {
                const match = normalizeText(headerText).match(/(January|February|March|April|May|June|July|August|September|October|November|December)\s*(\d{4})?/i);
                if (!match) return null;

                const month = monthNames.indexOf(match[1].toLowerCase()) + 1;
                if (!month) return null;

                return {
                    month,
                    year: match[2] ? parseInt(match[2], 10) : year
                };
            };

            const monthHeaders = Array.from(document.querySelectorAll(
                '.ScheduleListByMonth__monthHeader .ScheduleSection__sectionTitle, .ScheduleSection__stickyItem.StickyItem__stickyItem .ScheduleSection__sectionTitle'
            ))
                .map((el) => {
                    const parsed = parseMonthHeader(el.textContent || '');
                    return parsed ? { el, ...parsed } : null;
                })
                .filter(Boolean);

            const getMonthYearForRow = (row) => {
                let current = null;

                for (const header of monthHeaders) {
                    if (header.el === row || header.el.contains(row)) {
                        current = { month: header.month, year: header.year };
                        break;
                    }

                    const position = header.el.compareDocumentPosition(row);
                    if (position & Node.DOCUMENT_POSITION_FOLLOWING) {
                        current = { month: header.month, year: header.year };
                    } else if (position & Node.DOCUMENT_POSITION_PRECEDING) {
                        break;
                    }
                }

                return current;
            };

            const extractDayOfMonth = (row) => {
                const dateSources = [
                    row.querySelector('.ScheduleListByMonth__dayDate')?.textContent,
                    row.querySelector('.ScheduleListByMonth__date')?.textContent,
                    row.querySelector('.ScheduleListByMonth__dayLabel')?.textContent,
                    row.querySelector('time')?.textContent
                ];

                for (const source of dateSources) {
                    const text = normalizeText(source || '');
                    if (!text) continue;

                    const match = text.match(/(\d{1,2})$/);
                    if (match) {
                        const day = parseInt(match[1], 10);
                        if (day >= 1 && day <= 31) return day;
                    }
                }

                return null;
            };

            const normalizeScore = (scoreText) => {
                const match = normalizeText(scoreText || '').match(/(\d+)\s*-\s*(\d+)/);
                return match ? `${match[1]}-${match[2]}` : '';
            };

            const extractResultAndScore = (text) => {
                const normalized = normalizeText(text);
                const resultAndScore = normalized.match(/([WL])\s*(\d+\s*-\s*\d+)/i);

                if (resultAndScore) {
                    return {
                        result: resultAndScore[1].toUpperCase(),
                        score: normalizeScore(resultAndScore[2])
                    };
                }

                return {
                    result: '',
                    score: normalizeScore(normalized)
                };
            };

            const cleanOpponentText = (value) => normalizeText(value)
                .replace(/([WL])\s*\d+\s*-\s*\d+/gi, '')
                .replace(/\bLIVE\b/gi, '')
                .replace(/\d+\s*-\s*\d+/gi, '')
                .replace(/\b\d{1,2}:\d{2}\s*(AM|PM)\b/gi, '')
                .replace(/\b(FINAL|HOME|AWAY)\b/gi, '')
                .replace(/([A-Za-z])([WL])$/, '$1')
                .replace(/\b([WL])$/, '')
                .replace(/@(?=\S)/g, '@ ')
                .replace(/\bvs(?=\S)/gi, 'vs ')
                .replace(/^[•|\-]+\s*/, '')
                .replace(/\s{2,}/g, ' ')
                .trim();

            const extractOpponent = (link, rowText, linkText, eventContainerText) => {
                const opponentCandidates = [
                    '[class*="opponent"]',
                    '[class*="Opponent"]',
                    '[class*="teamName"]',
                    '[class*="TeamName"]'
                ];

                for (const selector of opponentCandidates) {
                    const candidate = cleanOpponentText(link.querySelector(selector)?.textContent || '');
                    if (candidate) return candidate;
                }

                return (
                    cleanOpponentText(linkText) ||
                    cleanOpponentText(eventContainerText) ||
                    cleanOpponentText(rowText) ||
                    'Unknown Opponent'
                );
            };

            // Match times like "3:00 PM", "10:30 AM"
            const timeRegex = /\b\d{1,2}:\d{2}\s*(AM|PM)\b/i;

            const extracted = [];
            const rows = document.querySelectorAll('div.ScheduleSection__section div.ScheduleListByMonth__dayRow');

            rows.forEach((row, rowIndex) => {
                const rowText = normalizeText(row.textContent || '');
                const monthYear = getMonthYearForRow(row);
                const dayOfMonth = extractDayOfMonth(row);

                let formattedDate = 'Unknown Date';
                if (monthYear?.month && dayOfMonth) {
                    const parsedDate = new Date(monthYear.year || year, monthYear.month - 1, dayOfMonth);
                    if (!Number.isNaN(parsedDate.getTime())) {
                        formattedDate = `${parsedDate.getMonth() + 1}/${parsedDate.getDate()}`;
                    } else {
                        formattedDate = `${monthYear.month}/${dayOfMonth}`;
                    }
                }

                const gameLinks = row.querySelectorAll('a.ScheduleListByMonth__event');

                gameLinks.forEach((link, linkIndex) => {
                    const href = link.getAttribute('href');
                    if (!href) return;

                    const linkText = normalizeText(link.textContent || '');
                    const eventContainerText = normalizeText(
                        link.closest('[class*="event"]')?.textContent ||
                        link.parentElement?.textContent ||
                        linkText
                    );
                    const statusText = normalizeText(
                        Array.from(link.querySelectorAll('[class*="status"], [class*="result"], [class*="score"], [data-testid*="score"]'))
                            .map((el) => el.textContent || '')
                            .join(' ')
                    );

                    const combinedText = normalizeText([linkText, eventContainerText, statusText].filter(Boolean).join(' '));
                    const { result, score } = extractResultAndScore(combinedText);

                    const hasScore = Boolean(score);
                    const hasTimeOnly = !hasScore && timeRegex.test(combinedText);

                    // Skip if game only has a time (not played yet)
                    if (hasTimeOnly) {
                        return;
                    }

                    const fullGameUrl = href.startsWith('http') ? href : `https://web.gc.com${href}`;
                    const gameUrl = fullGameUrl.replace(/\/$/, '').split('?')[0];
                    const gameIdMatch = gameUrl.match(/\/game\/([^/?#]+)/i);
                    const id = gameIdMatch ? `game-${gameIdMatch[1]}` : `game-${rowIndex}-${linkIndex}`;

                    extracted.push({
                        id,
                        opponent: extractOpponent(link, rowText, linkText, eventContainerText),
                        result,
                        date: formattedDate,
                        rawDate: dayOfMonth ? `${monthYear?.month || ''}/${dayOfMonth}` : '',
                        score,
                        gameUrl,
                        isCompleted: hasScore
                    });
                });
            });

            return extracted;
        }, currentYear);

        const normalizedGames = games.map(game => ({
            ...game,
            date: normalizeDateForOutput(game.date)
        }));
        // Attach owner team name as a non-enumerable property so JSON/array
        // iteration is unaffected; preview-multi-source reads it directly.
        Object.defineProperty(normalizedGames, 'ownerTeamName', {
            value: ownerTeamName || '',
            enumerable: false,
            writable: false,
            configurable: true
        });
        return normalizedGames;
    } catch (error) {
        throw new Error(error.message || 'Unable to extract game metadata from schedule.');
    } finally {
        if (page && !page.isClosed()) {
            await page.close().catch(() => {});
        }
        if (browser) {
            await browser.close().catch(() => {});
        }
    }
}

// This function now ONLY scrapes game data, assuming it's already on the schedule page.
async function scrapeDataFromSchedulePage(browser, page, scheduleUrl, statusCallback, selectedGameUrls = null) {
    const emitStatus = (message) => {
        if (typeof statusCallback === 'function') {
            statusCallback(message);
        }
    };

    // TEST MODE: Return mock data instantly without browser automation
    if (TEST_MODE) {
        emitStatus('MOCK MODE: Loading test data...');

        const normalizedSelectedUrls = Array.isArray(selectedGameUrls) && selectedGameUrls.length > 0
            ? new Set(selectedGameUrls.map(normalizeGameUrl).filter(Boolean))
            : null;

        const filteredMockGames = (normalizedSelectedUrls
            ? MOCK_DATA.mockGamesData.filter(game => normalizedSelectedUrls.has(normalizeGameUrl(game.gameUrl)))
            : MOCK_DATA.mockGamesData
        ).map(game => ({ ...game, boxScore: enrichBoxScoreWithJerseyNumbers(game.boxScore) }));

        if (filteredMockGames.length === 0) {
            throw new Error('Could not find any matching games on the provided schedule page.');
        }

        // Simulate realistic delays for status updates to mimic real scraping
        await new Promise(r => setTimeout(r, 100));
        emitStatus(`MOCK MODE: Found ${filteredMockGames.length} games. Beginning data aggregation...`);

        for (let i = 0; i < filteredMockGames.length; i++) {
            const mockGame = filteredMockGames[i];
            const mockOpponent = mockGame?.boxScore?.homeTeamName || mockGame?.boxScore?.awayTeamName || 'Unknown Opponent';
            const mockUrl = normalizeGameUrl(mockGame?.gameUrl) || mockGame?.gameUrl || 'Unknown URL';

            await new Promise(r => setTimeout(r, 100));
            emitStatus(`MOCK MODE: Processing game ${i + 1}/${filteredMockGames.length}: ${mockOpponent} (${mockUrl})`);
        }

        await new Promise(r => setTimeout(r, 100));
        emitStatus('MOCK MODE: Finalizing report...');

        const mockResult = MOCK_DATA.getMockScrapeResult();

        return {
            ...mockResult,
            allGamesData: filteredMockGames,
            teamLogoData: mockResult.teamLogoUrl,
            browser,
            page,
            scrapeSummary: {
                totalGamesDiscovered: filteredMockGames.length,
                totalGamesEligible: filteredMockGames.length,
                totalGamesAttempted: filteredMockGames.length,
                successfulGames: filteredMockGames.length,
                boxScoreOnlyGames: 0,
                noDataSkips: 0,
                infraErrors: 0,
                otherGameErrors: 0,
                fatalBrowserError: false,
                fatalReason: null,
                selectedGameMode: Boolean(normalizedSelectedUrls),
                errors: []
            }
        };
    }

    let workingBrowser = browser;
    let workingSchedulePage = page;
    let gameDataPage = null;
    let consecutiveBrowserRecoveryFailures = 0;

    const sessionMeta = getBrowserSessionMeta(workingBrowser, workingSchedulePage);

    const scrapeSummary = {
        totalGamesDiscovered: 0,
        totalGamesEligible: 0,
        totalGamesAttempted: 0,
        successfulGames: 0,
        boxScoreOnlyGames: 0,
        noDataSkips: 0,
        infraErrors: 0,
        otherGameErrors: 0,
        fatalBrowserError: false,
        fatalReason: null,
        selectedGameMode: Boolean(Array.isArray(selectedGameUrls) && selectedGameUrls.length > 0),
        errors: []
    };

    const createPage = async (targetBrowser) => {
        const createdPage = await targetBrowser.newPage();
        await createdPage.setViewport({ width: 1280, height: 800 });
        await setupGamePageInterception(createdPage);

        const meta = getBrowserSessionMeta(targetBrowser, workingSchedulePage);
        if (meta) {
            createdPage.__scoutSessionMeta = meta;
        }

        return createdPage;
    };

    const openSchedulePage = async () => {
        if (!isBrowserConnected(workingBrowser)) {
            throw new Error('Browser disconnected while preparing schedule page.');
        }

        if (!workingSchedulePage || workingSchedulePage.isClosed()) {
            workingSchedulePage = await createPage(workingBrowser);
        }

        await workingSchedulePage.goto(scheduleUrl, { waitUntil: 'domcontentloaded', timeout: 60000 });
        await workingSchedulePage.waitForSelector('div.ScheduleSection__section', { timeout: 30000 });
    };

    const relaunchBrowserContext = async (reason) => {
        if (!sessionMeta?.userDataPath) {
            throw new Error('Browser session metadata is missing. Unable to relaunch authenticated browser context.');
        }

        console.warn(`[SCRAPER][INFRA_BROWSER] Relaunching browser context. Reason: ${reason}`);

        await closePageSafely(gameDataPage);
        gameDataPage = null;

        await closePageSafely(workingSchedulePage);
        workingSchedulePage = null;

        await closeBrowserSafely(workingBrowser);

        workingBrowser = await puppeteer.launch(buildBrowserLaunchOptions({ userDataDir: sessionMeta.userDataPath }));
        attachBrowserSessionMeta(workingBrowser, sessionMeta);

        workingSchedulePage = await createPage(workingBrowser);
        await openSchedulePage();

        gameDataPage = await createPage(workingBrowser);
    };

    try {
        emitStatus('Accessing schedule page...');

        await openSchedulePage();

        const { teamLogoUrl, teamRecord } = await workingSchedulePage.evaluate(() => {
            const img = document.querySelector('img.Image__circle');
            const recordSpan = document.querySelector('span.NewTeamNavBar__teamDetailText');
            return {
                teamLogoUrl: img ? img.src : null,
                teamRecord: recordSpan ? recordSpan.innerText.trim() : null
            };
        });

        console.log(`[Scraper] Extracted team logo URL: ${teamLogoUrl || 'none'}, record: ${teamRecord || 'none'}`);

        // Fetch logo image immediately (URL expires quickly)
        let teamLogoData = null;
        if (teamLogoUrl) {
            try {
                teamLogoData = await fetchImageAsBase64(teamLogoUrl);
                console.log(`[Scraper] Successfully fetched logo image, size: ${teamLogoData ? teamLogoData.length : 0} chars`);
            } catch (error) {
                console.error(`[Scraper] Failed to fetch logo image: ${error.message}`);
            }
        }

        const gamesWithMetadata = await workingSchedulePage.evaluate(() => {
            const normalizeText = (value) => (value || '').replace(/\s+/g, ' ').trim();
            const cleanOpponentText = (value) => normalizeText(value)
                .replace(/([WL])\s*\d+\s*-\s*\d+/gi, '')
                .replace(/\bLIVE\b/gi, '')
                .replace(/\d+\s*-\s*\d+/gi, '')
                .replace(/\b\d{1,2}:\d{2}\s*(AM|PM)\b/gi, '')
                .replace(/\b(FINAL|HOME|AWAY)\b/gi, '')
                .replace(/([A-Za-z])([WL])$/, '$1')
                .replace(/\b([WL])$/, '')
                .replace(/@(?=\S)/g, '@ ')
                .replace(/\bvs(?=\S)/gi, 'vs ')
                .replace(/^[•|\-]+\s*/, '')
                .replace(/\s{2,}/g, ' ')
                .trim();

            const extractOpponentFromLink = (link, linkText, eventContainerText) => {
                const opponentCandidates = [
                    '[class*="opponent"]',
                    '[class*="Opponent"]',
                    '[class*="teamName"]',
                    '[class*="TeamName"]'
                ];

                for (const selector of opponentCandidates) {
                    const candidate = cleanOpponentText(link.querySelector(selector)?.textContent || '');
                    if (candidate) return candidate;
                }

                return cleanOpponentText(linkText) || cleanOpponentText(eventContainerText) || 'Unknown Opponent';
            };

            const normalizeScore = (scoreText) => {
                const match = normalizeText(scoreText || '').match(/(\d+)\s*-\s*(\d+)/);
                return match ? `${match[1]}-${match[2]}` : '';
            };

            const extractResultAndScore = (text) => {
                const normalized = normalizeText(text);
                const resultAndScore = normalized.match(/([WL])\s*(\d+\s*-\s*\d+)/i);

                if (resultAndScore) {
                    return {
                        result: resultAndScore[1].toUpperCase(),
                        score: normalizeScore(resultAndScore[2])
                    };
                }

                return {
                    result: '',
                    score: normalizeScore(normalized)
                };
            };

            const timeRegex = /\b\d{1,2}:\d{2}\s*(AM|PM)\b/i;
            const gameEntries = [];
            const rowSelector = 'div.ScheduleSection__section div.ScheduleListByMonth__dayRow:has(a.ScheduleListByMonth__event)';
            const linkSelector = 'a.ScheduleListByMonth__event';
            const gameRows = document.querySelectorAll(rowSelector);

            gameRows.forEach(row => {
                const linksInRow = row.querySelectorAll(linkSelector);
                linksInRow.forEach(link => {
                    const gamePath = link.getAttribute('href');
                    if (!gamePath) return;

                    const fullGameUrl = gamePath.startsWith('http') ? gamePath : `https://web.gc.com${gamePath}`;
                    const gameUrl = fullGameUrl.replace(/\/$/, '').split('?')[0];
                    const linkText = normalizeText(link.textContent || '');
                    const eventContainerText = normalizeText(
                        link.closest('[class*="event"]')?.textContent ||
                        link.parentElement?.textContent ||
                        linkText
                    );
                    const statusText = normalizeText(
                        Array.from(link.querySelectorAll('[class*="status"], [class*="result"], [class*="score"], [data-testid*="score"]'))
                            .map((el) => el.textContent || '')
                            .join(' ')
                    );

                    const combinedText = normalizeText([linkText, eventContainerText, statusText].filter(Boolean).join(' '));
                    const { score } = extractResultAndScore(combinedText);
                    const hasScore = Boolean(score);
                    const hasTimeOnly = !hasScore && timeRegex.test(combinedText);

                    gameEntries.push({
                        gameUrl,
                        opponent: extractOpponentFromLink(link, linkText, eventContainerText),
                        isCompleted: hasScore,
                        hasTimeOnly
                    });
                });
            });

            return gameEntries;
        });

        const normalizedSelectedUrls = Array.isArray(selectedGameUrls) && selectedGameUrls.length > 0
            ? new Set(selectedGameUrls.map(normalizeGameUrl).filter(Boolean))
            : null;

        scrapeSummary.totalGamesDiscovered = gamesWithMetadata.length;

        const filteredGames = normalizedSelectedUrls
            ? gamesWithMetadata.filter(game => normalizedSelectedUrls.has(normalizeGameUrl(game.gameUrl)))
            : gamesWithMetadata.filter(game => game.isCompleted);

        scrapeSummary.totalGamesEligible = filteredGames.length;

        if (!filteredGames || filteredGames.length === 0) {
            if (normalizedSelectedUrls) {
                throw new Error('Could not find any matching games on the provided schedule page.');
            }

            throw new Error('No completed games were found on the provided schedule page.');
        }

        const foundLabel = normalizedSelectedUrls
            ? `${filteredGames.length} selected games`
            : `${filteredGames.length} completed games`;

        emitStatus(`Found ${foundLabel}. Beginning data aggregation...`);

        const allGamesData = [];
        let gamesProcessed = 0;

        gameDataPage = await createPage(workingBrowser);

        for (const gameMeta of filteredGames) {
            const gameUrl = gameMeta.gameUrl;
            const opponent = gameMeta.opponent || 'Unknown Opponent';
            const normalizedGameUrl = normalizeGameUrl(gameUrl) || gameUrl;

            scrapeSummary.totalGamesAttempted += 1;
            emitStatus(`Processing game ${gamesProcessed + 1}/${filteredGames.length}: ${opponent} (${normalizedGameUrl})`);

            let gameAttempt = 0;
            let gameFinished = false;

            while (!gameFinished && gameAttempt < 2) {
                gameAttempt += 1;

                try {
                    if (!isBrowserConnected(workingBrowser)) {
                        throw new Error('Browser disconnected before game scrape.');
                    }

                    if (!gameDataPage || gameDataPage.isClosed()) {
                        gameDataPage = await createPage(workingBrowser);
                    }

                    await gameDataPage.goto(`${gameUrl}/box-score`, { waitUntil: 'domcontentloaded', timeout: 30000 });
                    await gameDataPage.waitForNetworkIdle({ idleTime: 750, timeout: 5000 }).catch(() => {});
                    await gameDataPage.waitForSelector('span.BoxScoreComponents__playerName', { timeout: 15000 });

                    if (await detectPaywall(gameDataPage)) {
                        throw new Error('PREMIUM_ACCESS_REQUIRED');
                    }

                    const boxScoreData = enrichBoxScoreWithJerseyNumbers(await gameDataPage.evaluate(scrapeBoxScoreFromPage));

                    if (await detectPaywall(gameDataPage, { requireBlurredCells: true })) {
                        throw new Error('PREMIUM_ACCESS_REQUIRED');
                    }

                    await gameDataPage.goto(`${gameUrl}/plays`, { waitUntil: 'domcontentloaded', timeout: 30000 });

                    if (await detectPaywall(gameDataPage)) {
                        throw new Error('PREMIUM_ACCESS_REQUIRED');
                    }

                    await gameDataPage.waitForSelector('div.BatsPlays__play', { timeout: 15000 });
                    let playsData = await gameDataPage.evaluate(scrapePlaysFromPage);

                    if ((!playsData || playsData.length === 0) && ((boxScoreData?.hitting?.length || 0) > 0 || (boxScoreData?.pitching?.length || 0) > 0)) {
                        console.warn(`[SCRAPER][RETRY_PLAYS] Empty plays payload for ${normalizedGameUrl}. Retrying plays scrape once.`);
                        await gameDataPage.goto(`${gameUrl}/plays`, { waitUntil: 'networkidle2', timeout: 45000 });
                        await gameDataPage.waitForSelector('div.BatsPlays__play', { timeout: 20000 });
                        playsData = await gameDataPage.evaluate(scrapePlaysFromPage);
                    }

                    const gameData = { gameUrl, plays: playsData, boxScore: boxScoreData };
                    const playsCount = gameData?.plays?.length || 0;
                    const hittingCount = gameData?.boxScore?.hitting?.length || 0;
                    const pitchingCount = gameData?.boxScore?.pitching?.length || 0;
                    const hasBoxScoreData = hittingCount > 0 || pitchingCount > 0;
                    const hasCompleteGameData = playsCount > 0 && hasBoxScoreData;

                    if (hasCompleteGameData) {
                        allGamesData.push(gameData);
                        scrapeSummary.successfulGames += 1;
                    } else {
                        if (hasBoxScoreData && playsCount === 0) {
                            scrapeSummary.boxScoreOnlyGames += 1;
                        }

                        scrapeSummary.noDataSkips += 1;
                        scrapeSummary.errors.push({
                            type: GAME_ERROR_TYPES.NO_DATA,
                            gameUrl: normalizedGameUrl,
                            gameIndex: gamesProcessed + 1,
                            attempt: gameAttempt,
                            message: `Game returned incomplete data (plays=${playsCount}, hitting=${hittingCount}, pitching=${pitchingCount}).`
                        });
                        console.log(`[SCRAPER][NO_DATA] Incomplete game data for ${normalizedGameUrl}. Skipping. (plays=${playsCount}, hitting=${hittingCount}, pitching=${pitchingCount})`);
                    }

                    consecutiveBrowserRecoveryFailures = 0;
                    gameFinished = true;
                } catch (gameError) {
                    const errorType = classifyGameError(gameError, workingBrowser, gameDataPage);
                    const errorEntry = {
                        type: errorType,
                        gameUrl: normalizedGameUrl,
                        gameIndex: gamesProcessed + 1,
                        attempt: gameAttempt,
                        message: gameError.message
                    };

                    scrapeSummary.errors.push(errorEntry);

                    if (errorType === GAME_ERROR_TYPES.PREMIUM_ACCESS_REQUIRED) {
                        console.error(`[SCRAPER][PREMIUM_ACCESS_REQUIRED] ${normalizedGameUrl} failed: ${gameError.message}`);
                        throw gameError;
                    }

                    if (errorType === GAME_ERROR_TYPES.INFRA_BROWSER) {
                        scrapeSummary.infraErrors += 1;
                        console.error(`[SCRAPER][INFRA_BROWSER] ${normalizedGameUrl} failed on attempt ${gameAttempt}: ${gameError.message}`);

                        try {
                            await relaunchBrowserContext(`game ${normalizedGameUrl} failed: ${gameError.message}`);
                            consecutiveBrowserRecoveryFailures = 0;
                        } catch (recoveryError) {
                            consecutiveBrowserRecoveryFailures += 1;
                            scrapeSummary.infraErrors += 1;
                            scrapeSummary.errors.push({
                                type: GAME_ERROR_TYPES.INFRA_BROWSER,
                                gameUrl: normalizedGameUrl,
                                gameIndex: gamesProcessed + 1,
                                attempt: gameAttempt,
                                stage: 'recovery',
                                message: recoveryError.message
                            });

                            console.error(
                                `[SCRAPER][INFRA_BROWSER] Recovery failed (${consecutiveBrowserRecoveryFailures}/${SCRAPER_MAX_BROWSER_RECOVERY_FAILURES}) for ${normalizedGameUrl}: ${recoveryError.message}`
                            );

                            if (consecutiveBrowserRecoveryFailures >= SCRAPER_MAX_BROWSER_RECOVERY_FAILURES) {
                                scrapeSummary.fatalBrowserError = true;
                                scrapeSummary.fatalReason = 'Browser recovery failed repeatedly during game scraping.';
                                throw new Error('Fatal browser recovery failure while scraping report games.');
                            }
                        }

                        if (gameAttempt < 2 && !scrapeSummary.fatalBrowserError) {
                            emitStatus(`Browser recovered. Retrying game ${gamesProcessed + 1}/${filteredGames.length}...`);
                            continue;
                        }

                        gameFinished = true;
                        continue;
                    }

                    consecutiveBrowserRecoveryFailures = 0;

                    if (errorType === GAME_ERROR_TYPES.NO_DATA) {
                        scrapeSummary.noDataSkips += 1;
                        console.log(`[SCRAPER][NO_DATA] ${normalizedGameUrl} skipped: ${gameError.message}`);
                    } else {
                        scrapeSummary.otherGameErrors += 1;
                        console.error(`[SCRAPER][OTHER_GAME_ERROR] ${normalizedGameUrl} failed: ${gameError.message}`);
                    }

                    gameFinished = true;
                }
            }

            gamesProcessed += 1;

            if (scrapeSummary.fatalBrowserError) {
                break;
            }
        }

        await closePageSafely(gameDataPage);
        gameDataPage = null;

        emitStatus('Finalizing report...');

        return {
            allGamesData,
            teamLogoData,
            teamRecord,
            scrapeSummary,
            browser: workingBrowser,
            page: workingSchedulePage
        };
    } catch (error) {
        await closePageSafely(gameDataPage);

        if (workingSchedulePage && !workingSchedulePage.isClosed()) {
            await workingSchedulePage.screenshot({ path: path.join(__dirname, 'error_screenshot.png') }).catch(() => {});
        }

        if (!error.scrapeSummary) {
            error.scrapeSummary = scrapeSummary;
        }

        if (!(error instanceof Error)) {
            throw new Error('An error occurred while preparing your report.');
        }

        throw error;
    }
}


// --- Main Exported Functions ---

module.exports = {
    buildExtraStatsGameNoteKey,
    enrichBoxScoreWithJerseyNumbers,
    buildCredentialFingerprint,
    resetGameChangerSessionState,
    clearInMemoryAuthState,
    clearPersistedAuthState,
    async performLogin(userId, gcEmail, gcPassword, statusCallback) {
        statusCallback('Initializing secure session...');
        
        // TEST MODE: Skip actual browser login, return mock success
        if (TEST_MODE) {
            statusCallback('MOCK MODE: Simulating login success...');
            await new Promise(r => setTimeout(r, 100));
            return { twoFactorRequired: false, browser: null, page: null };
        }
        
        const credentialFingerprint = buildCredentialFingerprint(gcEmail, gcPassword);
        const userDataRootPath = getUserRootDataPath(userId);
        const userDataPath = getUserDataPath(userId, credentialFingerprint);

        await fs.mkdir(userDataPath, { recursive: true });

        console.log(`[SCRAPER][AUTH_SESSION] Launching browser for user ${userId} with profile ${userDataPath} (fingerprint=${credentialFingerprint.slice(0, 12)}...).`);

        const browser = await puppeteer.launch(buildBrowserLaunchOptions({ userDataDir: userDataPath }));
        attachBrowserSessionMeta(browser, { userId, userDataPath, userDataRootPath, credentialFingerprint });

        const page = await browser.newPage();
        page.__scoutSessionMeta = getBrowserSessionMeta(browser);
        await page.setViewport({ width: 1280, height: 800 });

        try {
            statusCallback('Checking session status...');
            
            await page.goto('https://web.gc.com/teams', { waitUntil: 'networkidle2' });

            const loggedInSelector = 'span[data-testid="teams-title"]';
            const loginSelector = 'input[name="email"]';

            const raceResult = await Promise.race([
                page.waitForSelector(loggedInSelector, { timeout: 5000 }).then(() => 'loggedIn'),
                page.waitForSelector(loginSelector, { timeout: 5000 }).then(() => 'loginPage')
            ]).catch(() => 'timeout');

            if (raceResult === 'loggedIn') {
                statusCallback('Processing your request.');
                // Extract Firebase token for API access
                await module.exports._extractAndSaveFirebaseToken(page, userId);
                return { twoFactorRequired: false, browser, page };
            }

            if(raceResult === 'timeout') {
                await page.goto('https://web.gc.com/login', { waitUntil: 'networkidle2' });
            }

            statusCallback('Not logged in. Connecting to service...');

            const loginPageDiagnostics = await page.evaluate(async () => {
                const safeKeys = [];
                try {
                    for (let i = 0; i < localStorage.length; i += 1) {
                        const key = localStorage.key(i);
                        if (key) safeKeys.push(key);
                    }
                } catch (_) {}

                let serviceWorkerCount = 0;
                try {
                    if (navigator?.serviceWorker?.getRegistrations) {
                        const registrations = await navigator.serviceWorker.getRegistrations();
                        serviceWorkerCount = (registrations || []).length;
                    }
                } catch (_) {}

                return {
                    origin: location.origin,
                    localStorageKeys: safeKeys.slice(0, 15),
                    hasPersistRoot: safeKeys.includes('persist:root'),
                    serviceWorkerCount
                };
            }).catch(() => ({ origin: 'unknown', localStorageKeys: [], hasPersistRoot: false, serviceWorkerCount: 0 }));

            console.log(`[SCRAPER][AUTH_LOGIN] Login page diagnostics for user ${userId}: origin=${loginPageDiagnostics.origin}, serviceWorkers=${loginPageDiagnostics.serviceWorkerCount}, hasPersistRoot=${loginPageDiagnostics.hasPersistRoot}, localStorageKeys=${loginPageDiagnostics.localStorageKeys.join(',') || 'none'}`);

            await page.waitForSelector(loginSelector, { visible: true, timeout: 15000 });
            await page.click(loginSelector, { clickCount: 3 });
            await page.keyboard.press('Backspace');
            await page.focus(loginSelector);
            await page.type(loginSelector, gcEmail, { delay: 100 });

            const nextButtonSelector = 'button[data-testid="sign-in-button"]';
            await page.waitForSelector(nextButtonSelector, { visible: true, timeout: 5000 });
            await page.click(nextButtonSelector);
            
            // Check for password field OR email error
            try {
                await page.waitForSelector('input[name="password"]', { timeout: 5000 });
            } catch (e) {
                throw new Error("Invalid Team Credentials. Please check your email.");
            }

            // Check if 2FA is required *before* password (rare, but possible flow)
            const twoFactorSelector = 'input[name="code"]';
            let is2FARequired = await page.$(twoFactorSelector);

            if (is2FARequired) {
                statusCallback('Two-Factor Authentication required.');
                return { twoFactorRequired: true, browser, page };
            }
            
            const passwordFieldSelector = 'input[name="password"]';
            await page.click(passwordFieldSelector, { clickCount: 3 });
            await page.keyboard.press('Backspace');
            await page.type(passwordFieldSelector, gcPassword);
            await page.click('button[data-testid="sign-in-button"]::-p-text(Sign in)');
            
            // Race condition: Success vs 2FA vs Error
            try {
                const loginResult = await Promise.race([
                    page.waitForSelector(loggedInSelector, { timeout: 15000 }).then(() => 'loggedIn'),
                    page.waitForSelector(twoFactorSelector, { visible: true, timeout: 15000 }).then(() => '2fa')
                ]);

                if (loginResult === '2fa') {
                    statusCallback('Two-Factor Authentication required.');
                    return { twoFactorRequired: true, browser, page };
                }
            } catch (e) {
                // Timeout exceeded means we are stuck on the login page -> Password likely wrong.
                throw new Error("Invalid Team Credentials. Please check your password.");
            }

            // Extract Firebase token after successful login
            await module.exports._extractAndSaveFirebaseToken(page, userId);
            return { twoFactorRequired: false, browser, page };

        } catch (error) {
            console.error("[DEBUG] ERROR during login:", error.message);
            await page.screenshot({ path: path.join(__dirname, 'error_screenshot.png') });
            if (browser) await browser.close();
            // Pass through our custom error messages, otherwise generic
            throw new Error(error.message.includes('Invalid Team Credentials') ? error.message : 'An error occurred during the login process.');
        }
    },

    /**
     * Extract Firebase ID token from the page and save session for API usage
     * 
     * CRITICAL: This function navigates to an authenticated page first to trigger
     * GameChanger's automatic token refresh. The gc-token has a 1-hour lifetime
     * and must be refreshed by GameChanger's JavaScript before extraction.
     * 
     * @private
     */
    async _extractAndSaveFirebaseToken(page, userId) {
        try {
            console.log('[Scraper] Extracting auth tokens...');
            
            // STEP 1: Navigate to an authenticated page to trigger token refresh
            // GameChanger's JavaScript will automatically refresh the gc-token
            // when loading an authenticated page with an expired token
            console.log('[Scraper] Navigating to authenticated page to trigger token refresh...');
            try {
                await page.goto('https://web.gc.com/teams', { 
                    waitUntil: 'networkidle2', 
                    timeout: 30000 
                });
                console.log('[Scraper] Navigation complete, waiting for token refresh...');
                
                // Wait for GameChanger's JS to process and potentially refresh the token
                await new Promise(r => setTimeout(r, 3000));
            } catch (navError) {
                console.log('[Scraper] Navigation warning:', navError.message);
                // Continue anyway - we might already be on a valid page
            }
            
            // STEP 2: Check if we're authenticated
            const authStatus = await page.evaluate(() => {
                const persistRoot = localStorage.getItem('persist:root');
                const isAuthenticated = persistRoot && persistRoot.includes('"isAuthenticated":true');
                const edenToken = localStorage.getItem('eden-auth-tokens');
                return { isAuthenticated, hasEden: !!edenToken };
            });
            
            if (!authStatus.isAuthenticated) {
                console.log('[Scraper] WARNING: Not authenticated on GameChanger');
                console.log('[Scraper] Has eden token:', authStatus.hasEden);
                // Continue anyway - we might still have valid tokens
            } else {
                console.log('[Scraper] Authenticated session confirmed');
            }
            
            // STEP 3: Get all cookies and localStorage for session saving
            const cookies = await page.cookies();
            const localStorageData = await page.evaluate(() => {
                const data = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    data[key] = localStorage.getItem(key);
                }
                return data;
            });
            
            // Save session data for Puppeteer API client (in memory, not disk)
            const sessionData = {
                cookies: cookies,
                localStorage: localStorageData,
                extractedAt: new Date().toISOString()
            };
            
            // STEP 4: Extract the gc-token (should be fresh after navigation)
            let authData = null;
            
            // Method 1: Try localStorage (eden-auth-tokens)
            if (localStorageData['eden-auth-tokens']) {
                console.log('[Scraper] Found eden-auth-tokens in localStorage');
                authData = { edenTokens: localStorageData['eden-auth-tokens'] };
            }
            
            // Method 2: Session cookies
            const sessionCookies = cookies.filter(c => 
                c.name.includes('session') || 
                c.name.includes('auth') ||
                c.name.includes('token')
            );
            
            if (sessionCookies.length > 0) {
                console.log(`[Scraper] Found ${sessionCookies.length} session cookies`);
                authData = authData || {};
                authData.cookies = cookies;
            }
            
            // Method 3: Extract gc-token from localStorage
            console.log('[Scraper] Attempting to extract gc-token from localStorage...');
            const gcTokenData = await page.evaluate(() => {
                try {
                    const signatureKeys = Object.keys(localStorage).filter(k => 
                        k.startsWith('ab.storage.signature.')
                    );
                    
                    for (const key of signatureKeys) {
                        const value = localStorage.getItem(key);
                        if (value) {
                            try {
                                const parsed = JSON.parse(value);
                                if (parsed.v && parsed.v.startsWith('eyJ')) {
                                    return { 
                                        source: key, 
                                        token: parsed.v,
                                        fullData: parsed
                                    };
                                }
                            } catch (e) {
                                // Not JSON, skip
                            }
                        }
                    }
                    
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        const value = localStorage.getItem(key);
                        if (value && value.startsWith('eyJhbGci')) {
                            return { source: key, token: value };
                        }
                    }
                    
                    return null;
                } catch (e) {
                    return null;
                }
            });
            
            if (gcTokenData?.token) {
                console.log(`[Scraper] Found gc-token in ${gcTokenData.source}`);
                authData = authData || {};
                authData.gcToken = gcTokenData.token;
                
                // Log token expiry for debugging
                try {
                    const payload = JSON.parse(Buffer.from(gcTokenData.token.split('.')[1], 'base64').toString());
                    const expiryDate = new Date(payload.exp * 1000);
                    const now = new Date();
                    const minutesUntilExpiry = Math.floor((expiryDate - now) / 60000);
                    console.log(`[Scraper] Token expires at ${expiryDate.toISOString()} (${minutesUntilExpiry} minutes from now)`);
                } catch (e) {
                    // Ignore decode errors
                }
            } else {
                console.log('[Scraper] Could not find gc-token in localStorage');
            }
            
            // Also check for gc-token in cookies
            const gcTokenCookie = cookies.find(c => 
                c.name === 'gc-token' || c.name === 'gc_token'
            );
            if (gcTokenCookie && !authData?.gcToken) {
                console.log('[Scraper] Found gc-token in cookies');
                authData = authData || {};
                authData.gcToken = gcTokenCookie.value;
            }
            
            // Legacy: Firebase token
            const firebaseResult = await page.evaluate(() => {
                try {
                    if (typeof firebase !== 'undefined' && firebase.auth) {
                        const currentUser = firebase.auth().currentUser;
                        if (currentUser) {
                            const token = currentUser.stsTokenManager?.accessToken;
                            if (token) return { success: true, token };
                        }
                    }
                    return null;
                } catch (e) {
                    return null;
                }
            });
            
            if (firebaseResult?.token) {
                console.log('[Scraper] Found Firebase token (legacy)');
                authData = authData || {};
                authData.firebaseToken = firebaseResult.token;
            }
            
            if (authData) {
                authData.userId = userId;
                authData.extractedAt = new Date().toISOString();
                authData.sessionData = sessionData; // Include full session for API client
                
                // Save token to reports directory (writable disk on Render)
                // NOTE: This token will expire in ~1 hour. For long-term use,
                // navigate to an authenticated page again to trigger refresh.
                try {
                    const tokenFile = path.join(__dirname, 'reports', 'gc-token.json');
                    const tokenData = {
                        gcToken: authData.gcToken,
                        deviceId: '5acf3492aafb6a7fc2b58acb10fecf47',
                        savedAt: new Date().toISOString(),
                    };
                    // Try to decode and add expiry info
                    try {
                        const payload = JSON.parse(Buffer.from(authData.gcToken.split('.')[1], 'base64').toString());
                        tokenData.expiresAt = new Date(payload.exp * 1000).toISOString();
                        tokenData.payload = {
                            type: payload.type,
                            email: payload.email,
                            userId: payload.userId,
                        };
                    } catch (e) {
                        // Ignore decode errors
                    }
                    await fs.writeFile(tokenFile, JSON.stringify(tokenData, null, 2));
                    console.log(`[Scraper] Token saved to ${tokenFile}`);
                } catch (saveError) {
                    console.log(`[Scraper] Could not save token: ${saveError.message}`);
                }
                
                console.log('[Scraper] Auth data extracted successfully');
                return authData;
            } else {
                console.log('[Scraper] Could not extract any auth tokens');
                return null;
            }
        } catch (error) {
            console.error('[Scraper] Error extracting auth tokens:', error.message);
            return null;
        }
    },
    async submit2FACode(browser, page, code, gcPassword, statusCallback, userId) {
        try {
            statusCallback('Submitting verification code...');
            
            const codeSelector = 'input[name="code"]';
            const passwordSelector = 'input[name="password"]';
            const signInButtonSelector = 'button[data-testid="sign-in-button"]';
            const loggedInSelector = 'span[data-testid="teams-title"]';
            
            await page.waitForSelector(codeSelector, { visible: true, timeout: 10000 });
            await page.focus(codeSelector);
            await page.type(codeSelector, code, { delay: 100 });

            // Only enter password if the field is actually present and visible
            if (await page.$(passwordSelector) !== null) {
                 await page.waitForSelector(passwordSelector, { visible: true, timeout: 5000 });
                 await page.focus(passwordSelector);
                 await page.type(passwordSelector, gcPassword, { delay: 100 });
            }
            
            await page.waitForSelector(signInButtonSelector, { visible: true, timeout: 5000 });
            
            await page.click(signInButtonSelector);

            // ERROR CHECK: If we don't see the dashboard within 15s (reduced from 30s), fail.
            try {
                await page.waitForSelector(loggedInSelector, { timeout: 15000 });
            } catch (e) {
                throw new Error("Invalid Verification Code or Password. Please check both and try again.");
            }
            
            // Extract Firebase token after successful 2FA
            await module.exports._extractAndSaveFirebaseToken(page, userId);
            
            return { browser, page };
        } catch (error) {
            console.error("[DEBUG] ERROR during 2FA submission:", error.message);
            await page.screenshot({ path: path.join(__dirname, 'error_screenshot.png') });
            await browser.close();
            // Pass through our custom error, otherwise generic
            throw new Error(error.message.includes('Invalid') ? error.message : 'Failed to verify code. Please check the code and try again.');
        } 
    },

    extractGamesMetadata,
    scrapeDataFromSchedulePage
};
