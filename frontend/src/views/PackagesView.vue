<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">套餐管理</h2>
        <p class="page-subtitle">管理订阅来源、过滤规则和生成的订阅。</p>
      </div>
      <div class="page-actions">
        <div class="page-header-mark"><el-icon><Tickets /></el-icon><span>SUBSCRIPTIONS</span></div>
        <el-button @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>
          新建套餐
        </el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索套餐名称或订阅显示名称"
        clearable
        style="width: 260px"
      />
      <el-select
        v-model="statusFilter"
        placeholder="可用状态：全部"
        clearable
        style="width: 150px"
      >
        <el-option label="可用" value="available" />
        <el-option label="已停机" value="stopped" />
      </el-select>
      <el-select
        v-model="sortFilter"
        placeholder="排序：默认"
        clearable
        style="width: 190px"
      >
        <el-option label="到期日期：最近优先" value="expires_asc" />
        <el-option label="到期日期：最晚优先" value="expires_desc" />
        <el-option label="开通日期：最新优先" value="created_desc" />
        <el-option label="开通日期：最早优先" value="created_asc" />
      </el-select>
      <span class="filter-hint">客户端支持时每小时自动更新</span>
      <div class="spacer" />
      <el-radio-group
        v-model="displayMode"
        class="package-view-switch"
        size="small"
        aria-label="套餐视图"
        @change="persistDisplayMode"
      >
        <el-radio-button label="cards">
          <el-icon><Grid /></el-icon>
          卡片
        </el-radio-button>
        <el-radio-button label="details">
          <el-icon><List /></el-icon>
          详细列表
        </el-radio-button>
      </el-radio-group>
    </div>

    <div class="package-lookup-panel surface-card">
      <div class="package-lookup-copy">
        <strong>按订阅链接找套餐</strong>
        <span>支持完整订阅链接、Token 或 Token 前缀，结果只显示安全摘要</span>
      </div>
      <el-input
        v-model="packageLookupQuery"
        class="package-lookup-input"
        clearable
        placeholder="粘贴 https://.../sub/... 或 Token"
        @keyup.enter="findPackageBySubscription"
      >
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-button type="primary" :loading="packageLookupLoading" @click="findPackageBySubscription">查找套餐</el-button>
      <el-button v-if="packageLookupSearched" link @click="clearPackageLookup">清除结果</el-button>
    </div>

    <div v-if="packageLookupSearched" class="package-lookup-results surface-card">
      <div class="package-lookup-results-head">
        <strong>查找结果</strong>
        <span>{{ packageLookupResults.length ? `找到 ${packageLookupResults.length} 条匹配记录` : '未找到匹配套餐' }}</span>
      </div>
      <el-table v-if="packageLookupResults.length" :data="packageLookupResults" size="small" empty-text="未找到匹配套餐">
        <el-table-column label="套餐" min-width="190">
          <template #default="{ row }">
            <div class="package-lookup-main"><strong>{{ row.package_name }}</strong><span>{{ row.subscription_name }}</span></div>
          </template>
        </el-table-column>
        <el-table-column label="客户 / 经理" min-width="170">
          <template #default="{ row }">{{ row.customer_name || '套餐本身' }}<span v-if="row.manager_username" class="lookup-secondary"> · {{ row.manager_username }}</span></template>
        </el-table-column>
        <el-table-column label="Token 前缀" width="130"><template #default="{ row }">{{ row.token_prefix }}…</template></el-table-column>
        <el-table-column label="匹配方式" width="150"><template #default="{ row }">{{ packageLookupKindLabel(row.match_kind) }}</template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag size="small" :type="row.status === '生效中' ? 'success' : 'warning'">{{ row.status }}</el-tag></template></el-table-column>
        <el-table-column label="到期时间" width="170"><template #default="{ row }">{{ row.expires_at ? formatTime(row.expires_at) : '长期有效' }}</template></el-table-column>
        <el-table-column label="操作" width="110" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="openLookupPackage(row)">打开套餐</el-button></template></el-table-column>
      </el-table>
    </div>

    <div
      v-if="displayMode === 'cards'"
      v-loading="loading"
      class="package-grid"
    >
      <div
        v-for="(pkg, index) in paginatedPackages"
        :key="pkg.id"
        class="package-card"
        :class="{ 'notification-focus': String(pkg.id) === String(route.query.focus || '') }"
      >
        <div class="package-head">
          <div>
            <div class="package-name">
              <span class="package-index">#{{ packageIndex(index) }}</span>
              {{ pkg.name }}
              <el-tag
                :type="isAvailable(pkg) ? 'success' : 'danger'"
                effect="light"
                round
                size="small"
              >
                {{ isAvailable(pkg) ? '可用' : '已停机' }}
              </el-tag>
              <el-tag
                :type="isExpired(pkg) ? 'danger' : 'warning'"
                effect="light"
                round
                size="small"
              >
                {{ expirationLabel(pkg) }}
              </el-tag>
            </div>
          </div>
        </div>

        <div class="package-meta">
          <div class="meta-block">
            <div class="meta-label">订阅显示名称</div>
            <div class="meta-value">{{ pkg.subscription_name }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">Token 名称</div>
            <div class="meta-value">{{ pkg.token_name || '未命名' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">业务归属客户</div>
            <div class="meta-value">{{ pkg.owner_customer_name || '未指定' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">订阅源</div>
            <div class="meta-value">{{ summaryOf(pkg).sourceCount }} 个</div>
            <div v-if="missingSourcesOf(pkg).length" class="source-warning">
              已删除：{{ missingSourcesOf(pkg).join('、') }}
            </div>
          </div>
          <div class="meta-block">
            <div class="meta-label">当前可用节点</div>
            <div
              v-if="pkg.token_revoked_at"
              class="meta-value no-nodes"
            >
              Token 已吊销
            </div>
            <div
              v-else-if="(packageNodeCounts[pkg.id] ?? 0) > 0"
              class="meta-value"
            >
              {{ packageNodeCounts[pkg.id] }} 个可用节点
            </div>
            <div v-else class="meta-value no-nodes">
              0 个可用节点 / 当前无匹配节点
            </div>
          </div>
          <div class="meta-block">
            <div class="meta-label">包含关键词</div>
            <div class="meta-value">{{ summaryOf(pkg).includeText || '全部' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">排除关键词</div>
            <div class="meta-value">{{ summaryOf(pkg).excludeText || '无' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">重命名规则</div>
            <div class="meta-value">{{ summaryOf(pkg).renameText || '无' }}</div>
          </div>
          <div class="meta-block">
            <div class="meta-label">排序规则</div>
            <div class="meta-value">{{ summaryOf(pkg).sortText || '默认' }}</div>
          </div>
        </div>

        <div class="package-updated">
          <div>
            <span class="meta-label">开通日期</span>
            <span class="updated-value">{{ formatTime(pkg.created_at) }}</span>
          </div>
          <div class="package-date-end">
            <span class="meta-label">到期日期</span>
            <span class="updated-value">{{ pkg.expires_at ? formatTime(pkg.expires_at) : '长期有效' }}</span>
          </div>
        </div>

        <div class="package-usage">
          <span class="meta-label">实际使用客户</span>
          <el-button link type="primary" @click="showUsage(pkg)">{{ pkg.used_by_customers?.length || 0 }} 个客户</el-button>
          <span v-if="pkg.used_by_customers?.length" class="usage-names">{{ pkg.used_by_customers.slice(0, 3).map((item) => item.customer_name).join('、') }}{{ pkg.used_by_customers.length > 3 ? ' 等' : '' }}</span>
          <span v-else class="usage-empty">尚未开通给客户</span>
        </div>

        <div class="package-actions">
          <el-button size="default" type="primary" plain @click="openEdit(pkg)">
            编辑
          </el-button>
          <el-button
            size="default"
            plain
            @click="copyUrl(pkg)"
          >
            复制订阅
          </el-button>
          <el-button
            size="default"
            plain
            @click="showQr(pkg)"
          >
            二维码
          </el-button>
          <el-dropdown trigger="click" @command="(cmd) => handleMore(cmd, pkg)">
            <el-button size="default" plain>
              更多
              <el-icon><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="preview">预览节点</el-dropdown-item>
                <el-dropdown-item command="duplicate">复制套餐</el-dropdown-item>
                <el-dropdown-item command="regenerate">刷新 Token</el-dropdown-item>
                <el-dropdown-item command="toggle">
                  {{ pkg.enabled ? '禁用套餐' : '启用套餐' }}
                </el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除套餐</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div v-if="!loading && !filteredPackages.length" class="empty-state package-empty">
        <p class="empty-state-title">暂无套餐</p>
        <p class="empty-state-desc">创建一个套餐后，可以组合订阅来源并生成独立订阅。</p>
        <el-button type="primary" @click="openCreate">+ 新建套餐</el-button>
      </div>
    </div>

    <div
      v-else
      v-loading="loading"
      class="package-table-wrap surface-card"
    >
      <el-table
        :data="paginatedPackages"
        row-key="id"
        empty-text="暂无符合条件的套餐"
        :row-class-name="packageRowClassName"
      >
        <el-table-column label="#" width="64" align="center">
          <template #default="{ $index }">
            <span class="table-index">{{ packageIndex($index) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="套餐" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="package-table-main">
              <strong>{{ row.name }}</strong>
              <span>{{ row.subscription_name || '未设置订阅显示名称' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="归属与使用" min-width="190" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="package-table-main">
              <strong>{{ row.owner_customer_name || '未指定客户' }}</strong>
              <span v-if="row.used_by_customers?.length">
                {{ row.used_by_customers.slice(0, 2).map((item) => item.customer_name).join('、') }}{{ row.used_by_customers.length > 2 ? ' 等' : '' }}
              </span>
              <span v-else>尚未开通给客户</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="节点与来源" min-width="160">
          <template #default="{ row }">
            <div class="package-table-main">
              <strong :class="{ 'table-muted': (packageNodeCounts[row.id] ?? 0) === 0 }">
                {{ packageNodeCounts[row.id] ?? 0 }} 个可用节点
              </strong>
              <span>{{ summaryOf(row).sourceCount }} 个订阅源 · {{ (row.rules?.node_ids || []).length }} 个自有节点</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="开通 / 到期" min-width="180">
          <template #default="{ row }">
            <div class="package-table-main package-table-dates">
              <span>开通 {{ formatTime(row.created_at) }}</span>
              <span>到期 {{ row.expires_at ? formatTime(row.expires_at) : '长期有效' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <div class="package-table-status">
              <el-tag :type="isAvailable(row) ? 'success' : 'danger'" effect="light" size="small">
                {{ isAvailable(row) ? '可用' : '已停机' }}
              </el-tag>
              <span :class="{ 'table-danger': isExpired(row) }">{{ expirationLabel(row) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <div class="package-table-actions">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="primary" @click="copyUrl(row)">复制订阅</el-button>
              <el-button link type="primary" @click="showQr(row)">二维码</el-button>
              <el-dropdown trigger="click" @command="(cmd) => handleMore(cmd, row)">
                <el-button link type="primary">
                  更多
                  <el-icon><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="preview">预览节点</el-dropdown-item>
                    <el-dropdown-item command="duplicate">复制套餐</el-dropdown-item>
                    <el-dropdown-item command="regenerate">刷新 Token</el-dropdown-item>
                    <el-dropdown-item command="toggle">{{ row.enabled ? '禁用套餐' : '启用套餐' }}</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除套餐</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="filteredPackages.length" class="package-pagination">
      <span class="package-pagination-hint">共 {{ filteredPackages.length }} 个套餐</span>
      <el-pagination
        v-model:current-page="packagePage"
        v-model:page-size="packagePageSize"
        :page-sizes="packagePageSizes"
        layout="total, sizes, prev, pager, next, jumper"
        :total="filteredPackages.length"
        background
        @size-change="persistPackagePageSize"
      />
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editing ? '编辑套餐' : '新建套餐'"
      width="720px"
      append-to-body
    >
      <p class="dialog-subtitle">通过规则组合订阅源，生成独立的 Clash/Mihomo 订阅。</p>
      <el-form label-position="top">
        <div class="form-row">
          <el-form-item label="套餐名称" required style="flex: 1">
            <el-input v-model="form.name" placeholder="请输入套餐名称" />
          </el-form-item>
        <el-form-item label="订阅显示名称" style="flex: 1">
          <el-input v-model="form.subscription_name" placeholder="留空默认使用套餐名称" />
        </el-form-item>
        <el-form-item label="Token 名称">
          <el-input v-model="form.token_name" placeholder="例如：手机主订阅、电脑备用订阅" />
          <div class="form-hint">仅用于后台识别，不会改变订阅 Token 本身。</div>
        </el-form-item>
        </div>
        <el-form-item label="说明">
          <el-input v-model="form.description" placeholder="选填" />
        </el-form-item>
        <el-form-item label="业务归属客户">
          <div class="owner-picker">
            <el-select v-model="form.owner_customer_id" clearable filterable placeholder="选择客户或暂不指定" style="width: 100%">
              <el-option v-for="customer in customerOptions" :key="customer.id" :label="`${customer.name}${customer.region ? ` · ${customer.region}` : ''}`" :value="customer.id" />
            </el-select>
            <el-button @click="customerDialogVisible = true"><el-icon><Plus /></el-icon>新建客户</el-button>
          </div>
          <div class="form-hint">用于标记当前套餐的业务归属；实际开通给多个客户后，会在套餐列表中汇总显示。</div>
        </el-form-item>
        <el-form-item label="登录用户归属（兼容）">
          <el-select v-model="form.owner_user_id" clearable filterable placeholder="不指定则仅管理员管理" style="width: 100%">
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="user.username"
              :value="user.id"
            />
          </el-select>
          <div class="form-hint">保留原有普通用户订阅入口；业务客户请使用上面的客户归属。</div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="到期时间">
          <el-date-picker
            v-model="form.expires_at"
            type="datetime"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="留空表示永不过期"
            clearable
            style="width: 100%"
          />
          <div class="expiry-quick-actions">
            <span class="form-hint">快捷设置（从当前时间起）</span>
            <el-button-group>
              <el-button size="small" @click="setQuickExpiry(1)">1个月有效期</el-button>
              <el-button size="small" @click="setQuickExpiry(3)">3个月有效期</el-button>
              <el-button size="small" @click="setQuickExpiry(12)">1年有效期</el-button>
            </el-button-group>
          </div>
          <div class="form-hint">到期后订阅只返回不可连接的续费提示线路，旧缓存不会继续生效。</div>
        </el-form-item>

        <el-divider content-position="left">筛选规则</el-divider>
        <el-form-item label="节点来源">
          <div class="node-source-box">
            <div class="source-group">
              <div class="source-group-title">订阅源</div>
              <div class="source-check-list">
                <el-checkbox-group v-model="form.rules.source_filter">
                  <el-checkbox
                    v-for="source in sourceOptions"
                    :key="source"
                    :value="source"
                    class="source-check"
                  >
                    {{ source }}
                  </el-checkbox>
                </el-checkbox-group>
                <div v-if="!sourceOptions.length" class="form-hint">暂无订阅源</div>
              </div>
              <div v-if="missingFormSources.length" class="source-warning">
                当前套餐仍保留已删除来源：{{ missingFormSources.join('、') }}。这些来源不会扩大为全部来源，清除后才会从筛选规则中移除。
              </div>
              <div class="source-actions">
                <el-button size="small" @click="selectAllSources">全选</el-button>
                <el-button size="small" @click="form.rules.source_filter = []">清空</el-button>
              </div>
            </div>
            <div class="source-group">
              <div class="source-group-title">资源池</div>
              <el-select v-model="resourceFilter" clearable filterable style="width: 240px" placeholder="全部资源">
                <el-option label="全部资源" value="all" />
                <el-option label="上游订阅节点" value="category:subscription" />
                <el-option label="导入外部节点" value="category:external" />
                <el-option label="已转发节点" value="category:forwarded" />
                <el-option v-for="source in resourceSourceOptions" :key="`source-${source}`" :label="`来源：${source}`" :value="`source:${source}`" />
              </el-select>
              <el-input
                v-model="selfNodeSearch"
                placeholder="搜索编号、名称、服务器或备注"
                clearable
                style="width: 240px"
              />
              <div class="self-node-list">
                <el-checkbox-group v-model="form.rules.node_ids">
                  <el-checkbox
                    v-for="node in filteredSelfNodes"
                    :key="node.id"
                    :value="node.id"
                    class="self-node-check"
                  >
                    <span class="node-option-name">{{ node.node_code || '未编号' }} · {{ node.name }}</span>
                    <span class="node-option-meta">
                      {{ node.type }} · {{ node.country || '-' }} · {{ node.server }} · {{ node.note || '无备注' }}
                    </span>
                  </el-checkbox>
                </el-checkbox-group>
                <div v-if="!filteredSelfNodes.length" class="form-hint">暂无匹配的资源节点</div>
              </div>
              <div class="source-actions">
                <el-button size="small" @click="selectAllSelfNodes">全选</el-button>
                <el-button size="small" @click="form.rules.node_ids = []">清空</el-button>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="地区">
          <el-select v-model="form.rules.country_filter" multiple clearable style="width: 100%">
            <el-option v-for="country in countryOptions" :key="country" :label="country" :value="country" />
          </el-select>
          <div class="form-hint">按节点识别出的国家/地区过滤，例如：香港、台湾、美国。</div>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.rules.type_filter" multiple clearable style="width: 100%">
            <el-option label="VLESS" value="vless" />
            <el-option label="VMess" value="vmess" />
            <el-option label="Shadowsocks" value="shadowsocks" />
            <el-option label="Trojan" value="trojan" />
            <el-option label="AnyTLS" value="anytls" />
          </el-select>
        </el-form-item>

        <el-form-item label="包含关键词">
          <div class="keyword-box">
            <div class="keyword-add">
              <el-input
                v-model="includeKeywordInput"
                placeholder="输入关键词后点击添加，如：美国"
                style="width: 220px"
                @keyup.enter="addKeywordFrom('include_keywords')"
              />
              <el-button @click="addKeywordFrom('include_keywords')">
                添加
              </el-button>
            </div>
            <div v-if="form.rules.include_keywords.length" class="keyword-tags">
              <el-tag
                v-for="(value, index) in form.rules.include_keywords"
                :key="value"
                closable
                @close="removeKeyword('include_keywords', index)"
              >
                {{ value }}
              </el-tag>
            </div>
            <div v-else class="form-hint">尚未添加关键词</div>
          </div>
          <div class="form-hint">
            按节点名称过滤，只保留包含这些关键词的节点；与地区/类型同时设置时为 AND 关系，节点必须同时满足。
          </div>
        </el-form-item>
        <el-form-item label="排除关键词">
          <div class="keyword-box">
            <div class="keyword-add">
              <el-input
                v-model="excludeKeywordInput"
                placeholder="输入关键词后点击添加，如：香港"
                style="width: 220px"
                @keyup.enter="addKeywordFrom('exclude_keywords')"
              />
              <el-button @click="addKeywordFrom('exclude_keywords')">
                添加
              </el-button>
            </div>
            <div v-if="form.rules.exclude_keywords.length" class="keyword-tags">
              <el-tag
                v-for="(value, index) in form.rules.exclude_keywords"
                :key="value"
                closable
                @close="removeKeyword('exclude_keywords', index)"
              >
                {{ value }}
              </el-tag>
            </div>
            <div v-else class="form-hint">尚未添加关键词</div>
          </div>
          <div class="form-hint">
            按节点名称过滤，删除包含这些关键词的节点；与包含关键词同时设置时，先包含再排除。
          </div>
        </el-form-item>

        <el-divider content-position="left">重命名规则</el-divider>
        <el-form-item label="名称替换">
          <div class="rename-list">
            <div v-for="(item, index) in renameForm.replacements" :key="index" class="rename-row">
              <el-input v-model="item.from" placeholder="原名称，如：美国" style="width: 180px" />
              <span class="arrow">→</span>
              <el-input v-model="item.to" placeholder="替换为，如：US" style="width: 180px" />
              <el-button size="small" type="danger" plain @click="removeRename(index)">删除</el-button>
            </div>
            <el-button size="small" @click="addRename">+ 添加规则</el-button>
          </div>
          <div class="rule-options">
            <el-checkbox v-model="renameForm.country_abbr">国家缩写（香港→HK）</el-checkbox>
            <el-checkbox v-model="renameForm.numbered">自动编号（HK-01）</el-checkbox>
          </div>
          <div class="rule-extra">
            <el-input v-model="renameForm.prefix" placeholder="前缀，如：HK-" style="width: 170px" />
            <el-input v-model="renameForm.suffix" placeholder="后缀，如：-专线" style="width: 170px" />
          </div>
        </el-form-item>

        <el-divider content-position="left">排序规则</el-divider>
        <el-form-item label="排序字段">
          <el-select v-model="sortForm.field" style="width: 200px">
            <el-option label="国家" value="country" />
            <el-option label="来源" value="source" />
            <el-option label="类型" value="type" />
            <el-option label="名称" value="name" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先顺序">
          <div class="priority-add">
            <el-input
              v-model="priorityInput"
              placeholder="输入后回车添加，如：日本"
              style="width: 180px"
              @keyup.enter="addPriority"
            />
            <el-button @click="addPriority">添加</el-button>
          </div>
          <div v-if="sortForm.order.length" class="priority-list">
            <div v-for="(value, index) in sortForm.order" :key="value" class="priority-row">
              <span class="priority-index">{{ index + 1 }}</span>
              <span class="priority-value">{{ value }}</span>
              <el-button
                size="small"
                text
                :disabled="index === 0"
                @click="movePriority(index, -1)"
              >
                ↑
              </el-button>
              <el-button
                size="small"
                text
                :disabled="index === sortForm.order.length - 1"
                @click="movePriority(index, 1)"
              >
                ↓
              </el-button>
              <el-button size="small" text type="danger" @click="removePriority(index)">×</el-button>
            </div>
          </div>
          <div v-else class="form-hint">未设置优先顺序，按字段默认排序。</div>
        </el-form-item>
        <el-form-item label="排序方向">
          <el-radio-group v-model="sortForm.direction">
            <el-radio value="custom">自定义顺序</el-radio>
            <el-radio value="asc">正序</el-radio>
            <el-radio value="desc">倒序</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          保存套餐
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="套餐节点预览" width="760px" append-to-body>
      <el-table :data="previewRows" max-height="480">
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="country" label="地区" width="90" />
        <el-table-column prop="server" label="服务器" min-width="150" show-overflow-tooltip />
        <el-table-column prop="port" label="端口" width="80" />
        <el-table-column prop="source_name" label="来源" width="110" />
      </el-table>
    </el-dialog>

    <el-dialog v-model="qrVisible" :title="`订阅二维码 · ${qrName}`" width="380px" append-to-body>
      <div class="qr-body">
        <img v-if="qrDataUrl" :src="qrDataUrl" alt="订阅二维码" class="qr-image" />
        <div class="qr-url">{{ qrUrl }}</div>
        <el-button type="primary" plain @click="copyQrUrl">复制订阅地址</el-button>
      </div>
    </el-dialog>

    <el-dialog v-model="usageVisible" :title="`${usagePackage?.name || ''} · 使用客户`" width="620px" append-to-body>
      <el-table :data="usagePackage?.used_by_customers || []" empty-text="尚未开通给客户">
        <el-table-column prop="customer_name" label="客户" min-width="150" />
        <el-table-column prop="manager_username" label="负责经理" min-width="130"><template #default="{ row }">{{ row.manager_username || '未分配' }}</template></el-table-column>
        <el-table-column prop="subscription_count" label="订阅次数" width="100" />
        <el-table-column prop="active_subscription_count" label="生效中" width="90" />
      </el-table>
    </el-dialog>

    <el-dialog v-model="customerDialogVisible" title="快速新建客户" width="480px" append-to-body>
      <el-form label-position="top">
        <el-form-item label="客户名称" required><el-input v-model="customerForm.name" placeholder="例如：客户 A" /></el-form-item>
        <div class="form-row"><el-form-item label="地区"><el-input v-model="customerForm.region" placeholder="例如：香港" /></el-form-item><el-form-item label="联系方式"><el-input v-model="customerForm.contact" placeholder="手机号或其他联系方式" /></el-form-item></div>
        <el-form-item label="备注"><el-input v-model="customerForm.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="customerDialogVisible = false">取消</el-button><el-button type="primary" :loading="customerSaving" @click="quickCreateCustomer">创建并归属</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import QRCode from 'qrcode'
import {
  createPackage,
  duplicatePackage,
  deletePackage,
  getPackageSubscriptionUrl,
  getPackage,
  listPackages,
  listNodes,
  listSources,
  listCustomers,
  createCustomer,
  lookupPackages,
  previewPackage,
  listUsers,
  regenerateToken,
  togglePackage,
  updatePackage
} from '../api'
import { formatApiDate } from '../utils/datetime'

const countryOptions = [
  '香港', '台湾', '日本', '韩国', '新加坡', '美国', '英国',
  '德国', '法国', '马来西亚', '墨西哥', '俄罗斯', '澳大利亚',
  '加拿大', '泰国', '越南', '印度', '荷兰', '印尼', '菲律宾'
]

const packages = ref([])
const sourceOptions = ref([])
const sourcesLoaded = ref(false)
const userOptions = ref([])
const customerOptions = ref([])
const packageNodeCounts = ref({})
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const previewVisible = ref(false)
const previewRows = ref([])
const editing = ref(null)
const priorityInput = ref('')
const includeKeywordInput = ref('')
const excludeKeywordInput = ref('')
const selfNodes = ref([])
const selfNodeSearch = ref('')
const resourceFilter = ref('all')
const searchKeyword = ref('')
const packageLookupQuery = ref('')
const packageLookupResults = ref([])
const packageLookupLoading = ref(false)
const packageLookupSearched = ref(false)
const statusFilter = ref('')
const sortFilter = ref('')
const displayMode = ref(window.localStorage.getItem('packages-view-mode') || 'cards')
const packagePageSizes = [10, 20, 50, 100]
const savedPackagePageSize = Number(window.localStorage.getItem('packages-page-size'))
const packagePage = ref(1)
const packagePageSize = ref(packagePageSizes.includes(savedPackagePageSize) ? savedPackagePageSize : 20)
const nowTick = ref(Date.now())
const qrVisible = ref(false)
const qrDataUrl = ref('')
const qrUrl = ref('')
const qrName = ref('')
const usageVisible = ref(false)
const usagePackage = ref(null)
const customerDialogVisible = ref(false)
const customerSaving = ref(false)
const customerForm = reactive({ name: '', region: '', contact: '', note: '' })
const renameForm = reactive({
  prefix: '',
  suffix: '',
  replacements: [{ from: '', to: '' }],
  country_abbr: false,
  numbered: false
})
const sortForm = reactive({
  field: 'country',
  order: [],
  direction: 'custom'
})
const extraRenameRules = ref([])
const extraSortRules = ref([])
const form = reactive({
  name: '',
  subscription_name: '',
  token_name: '',
  description: '',
  enabled: true,
  expires_at: null,
  owner_user_id: null,
  owner_customer_id: null,
  rules: {
    source_filter: [],
    node_ids: [],
    country_filter: [],
    type_filter: [],
    include_keywords: [],
    exclude_keywords: []
  }
})
const route = useRoute()

const filteredPackages = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  const result = packages.value.filter((pkg) => {
    if (statusFilter.value === 'available' && !isAvailable(pkg)) return false
    if (statusFilter.value === 'stopped' && isAvailable(pkg)) return false
    if (keyword) {
      const name = `${pkg.name} ${pkg.subscription_name || ''}`.toLowerCase()
      if (!name.includes(keyword)) return false
    }
    return true
  })

  if (sortFilter.value) {
    result.sort((left, right) => comparePackages(left, right, sortFilter.value))
  }
  return result
})

const paginatedPackages = computed(() => {
  const start = (packagePage.value - 1) * packagePageSize.value
  return filteredPackages.value.slice(start, start + packagePageSize.value)
})

watch([searchKeyword, statusFilter, sortFilter], () => {
  packagePage.value = 1
})

const filteredSelfNodes = computed(() => {
  const keyword = selfNodeSearch.value.trim().toLowerCase()
  if (!keyword) {
    return filterResourceNodes(selfNodes.value)
  }
  return filterResourceNodes(selfNodes.value).filter((node) => {
    const text = `${node.node_code || ''} ${node.name} ${node.server} ${node.country || ''} ${node.note || ''}`.toLowerCase()
    return text.includes(keyword)
  })
})

const resourceSourceOptions = computed(() => [...new Set(selfNodes.value.map((node) => node.source_name).filter(Boolean))].sort())

function filterResourceNodes(nodes) {
  if (!resourceFilter.value || resourceFilter.value === 'all') return nodes
  if (resourceFilter.value.startsWith('category:')) {
    return nodes.filter((node) => node.node_category === resourceFilter.value.slice(9))
  }
  if (resourceFilter.value.startsWith('source:')) {
    return nodes.filter((node) => node.source_name === resourceFilter.value.slice(7))
  }
  return nodes
}

const missingFormSources = computed(() => {
  if (!sourcesLoaded.value) return []
  const availableSources = new Set(sourceOptions.value)
  return form.rules.source_filter.filter((source) => !availableSources.has(source))
})

function resetRuleForms() {
  Object.assign(renameForm, {
    prefix: '',
    suffix: '',
    replacements: [{ from: '', to: '' }],
    country_abbr: false,
    numbered: false
  })
  Object.assign(sortForm, {
    field: 'country',
    order: [],
    direction: 'custom'
  })
  priorityInput.value = ''
  extraRenameRules.value = []
  extraSortRules.value = []
}

function addRename() {
  renameForm.replacements.push({ from: '', to: '' })
}

function removeRename(index) {
  renameForm.replacements.splice(index, 1)
  if (!renameForm.replacements.length) {
    renameForm.replacements.push({ from: '', to: '' })
  }
}

function addKeywordFrom(key) {
  const inputRef =
    key === 'include_keywords' ? includeKeywordInput : excludeKeywordInput
  const value = inputRef.value.trim()
  if (!value) {
    return
  }
  const list = form.rules[key]
  if (!list.includes(value)) {
    list.push(value)
  }
  inputRef.value = ''
}

function removeKeyword(key, index) {
  form.rules[key].splice(index, 1)
}

function addPriority() {
  const value = priorityInput.value.trim()
  if (value && !sortForm.order.includes(value)) {
    sortForm.order.push(value)
  }
  priorityInput.value = ''
}

function removePriority(index) {
  sortForm.order.splice(index, 1)
}

function movePriority(index, direction) {
  const target = index + direction
  if (target < 0 || target >= sortForm.order.length) {
    return
  }
  const [item] = sortForm.order.splice(index, 1)
  sortForm.order.splice(target, 0, item)
}

function summaryOf(pkg) {
  const rules = pkg.rules || {}
  const replacements = (rules.rename_rules || []).flatMap((rule) => rule.replacements || [])
  return {
    sourceCount: (rules.source_filter || []).length,
    includeText: (rules.include_keywords || []).join(' / '),
    excludeText: (rules.exclude_keywords || []).join(' / '),
    renameText: replacements.map((item) => `${item.from}→${item.to}`).join(' / '),
    sortText: (rules.sort_rules || [])
      .map((rule) => `${rule.field}${rule.order && rule.order.length ? `：${rule.order.join('/')}` : ''}`)
      .join(' / ')
  }
}

function missingSourcesOf(pkg) {
  if (!sourcesLoaded.value) return []
  const availableSources = new Set(sourceOptions.value)
  return (pkg.rules?.source_filter || []).filter((source) => !availableSources.has(source))
}

async function load() {
  loading.value = true
  try {
    const { data } = await listPackages()
    packages.value = data
    await refreshNodeCounts()
    const focusId = String(route.query.focus || '')
    const focusIndex = focusId
      ? filteredPackages.value.findIndex((pkg) => String(pkg.id) === focusId)
      : -1
    if (focusIndex >= 0) {
      packagePage.value = Math.floor(focusIndex / packagePageSize.value) + 1
    }
    const maxPage = Math.max(1, Math.ceil(filteredPackages.value.length / packagePageSize.value))
    if (packagePage.value > maxPage) {
      packagePage.value = maxPage
    }
    await nextTick()
    document.querySelector('.notification-focus')?.scrollIntoView({ block: 'center' })
  } finally {
    loading.value = false
  }
}

async function refreshNodeCounts() {
  const entries = await Promise.all(
    packages.value.map(async (pkg) => {
      try {
        const { data } = await previewPackage(pkg.id)
        return [pkg.id, data.length]
      } catch {
        return [pkg.id, 0]
      }
    })
  )
  packageNodeCounts.value = Object.fromEntries(entries)
}

async function loadSources() {
  const { data } = await listSources()
  sourceOptions.value = data.items.map((item) => item.name)
  sourcesLoaded.value = true
}

async function loadUsers() {
  const { data } = await listUsers()
  userOptions.value = data.filter((user) => user.role === 'user' && user.is_active)
}

async function loadCustomers() {
  const { data } = await listCustomers()
  customerOptions.value = data.filter((customer) => customer.is_active)
}

function resetCustomerForm() {
  Object.assign(customerForm, { name: '', region: '', contact: '', note: '' })
}

async function quickCreateCustomer() {
  if (!customerForm.name.trim()) {
    ElMessage.warning('请输入客户名称')
    return
  }
  customerSaving.value = true
  try {
    const { data } = await createCustomer({ ...customerForm, name: customerForm.name.trim() })
    customerOptions.value = [data, ...customerOptions.value]
    form.owner_customer_id = data.id
    customerDialogVisible.value = false
    resetCustomerForm()
    ElMessage.success('客户已创建并归属到当前套餐')
  } finally {
    customerSaving.value = false
  }
}

function showUsage(pkg) {
  usagePackage.value = pkg
  usageVisible.value = true
}

async function loadSelfNodes() {
  const first = await listNodes({ page: 1, page_size: 100 })
  const nodes = [...first.data.items]
  const pages = Math.ceil(first.data.total / first.data.page_size)
  if (pages > 1) {
    const rest = await Promise.all(
      Array.from({ length: pages - 1 }, (_, index) => listNodes({ page: index + 2, page_size: 100 }))
    )
    rest.forEach(({ data }) => nodes.push(...data.items))
  }
  selfNodes.value = nodes.filter((node) => node.enabled)
}

function selectAllSources() {
  form.rules.source_filter = [...sourceOptions.value]
}

function selectAllSelfNodes() {
  const ids = new Set(form.rules.node_ids)
  filteredSelfNodes.value.forEach((node) => ids.add(node.id))
  form.rules.node_ids = [...ids]
}

function resetForm() {
  Object.assign(form, {
    name: '',
    subscription_name: '',
    token_name: '',
    description: '',
    enabled: true,
    expires_at: null,
    owner_user_id: null,
    owner_customer_id: null,
    rules: {
      source_filter: [],
      node_ids: [],
      country_filter: [],
      type_filter: [],
      include_keywords: [],
      exclude_keywords: []
    }
  })
  resourceFilter.value = 'all'
  includeKeywordInput.value = ''
  excludeKeywordInput.value = ''
  resetRuleForms()
}

function padNumber(value) {
  return String(value).padStart(2, '0')
}

function formatDatePickerValue(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return [
    date.getFullYear(),
    padNumber(date.getMonth() + 1),
    padNumber(date.getDate())
  ].join('-') + `T${padNumber(date.getHours())}:${padNumber(date.getMinutes())}:${padNumber(date.getSeconds())}`
}

function setQuickExpiry(months) {
  const now = new Date()
  const day = now.getDate()
  const target = new Date(now)
  target.setDate(1)
  target.setMonth(target.getMonth() + months)
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate()
  target.setDate(Math.min(day, lastDay))
  form.expires_at = formatDatePickerValue(target)
}

function toUtcIso(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function isExpired(pkg) {
  // 让页面长时间打开时，套餐到期状态也能自动切换。
  void nowTick.value
  return Boolean(pkg.expires_at && new Date(pkg.expires_at).getTime() <= nowTick.value)
}

function isAvailable(pkg) {
  return Boolean(pkg.enabled && !pkg.token_revoked_at && !isExpired(pkg))
}

function comparePackages(left, right, mode) {
  if (mode.startsWith('created_')) {
    const leftTime = dateTimestamp(left.created_at, 0)
    const rightTime = dateTimestamp(right.created_at, 0)
    return mode === 'created_asc'
      ? leftTime - rightTime || left.id - right.id
      : rightTime - leftTime || right.id - left.id
  }

  const leftTime = dateTimestamp(left.expires_at, Number.POSITIVE_INFINITY)
  const rightTime = dateTimestamp(right.expires_at, Number.POSITIVE_INFINITY)
  return mode === 'expires_asc'
    ? leftTime - rightTime || left.id - right.id
    : rightTime - leftTime || right.id - left.id
}

function dateTimestamp(value, emptyValue) {
  if (!value) return emptyValue
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? emptyValue : timestamp
}

function persistDisplayMode(value) {
  window.localStorage.setItem('packages-view-mode', value)
}

function persistPackagePageSize(value) {
  packagePage.value = 1
  window.localStorage.setItem('packages-page-size', String(value))
}

function packageIndex(index) {
  return (packagePage.value - 1) * packagePageSize.value + index + 1
}

function packageRowClassName({ row }) {
  return String(row.id) === String(route.query.focus || '') ? 'notification-focus' : ''
}

function expirationLabel(pkg) {
  if (!pkg.expires_at) return '长期有效'
  return isExpired(pkg) ? '已到期' : `有效至 ${formatTime(pkg.expires_at)}`
}

function openCreate() {
  editing.value = null
  resetForm()
  Promise.all([loadSelfNodes(), loadCustomers(), loadUsers()])
  dialogVisible.value = true
}

async function openEdit(row) {
  editing.value = row
  await Promise.all([loadSelfNodes(), loadCustomers(), loadUsers()])
  const { data } = await getPackage(row.id)
  Object.assign(form, {
    name: data.name,
    subscription_name: data.subscription_name || '',
    token_name: data.token_name || '',
    description: data.description || '',
    enabled: data.enabled,
    expires_at: formatDatePickerValue(data.expires_at),
    owner_user_id: data.owner_user_id,
    owner_customer_id: data.owner_customer_id,
    rules: {
      source_filter: data.rules.source_filter || [],
      node_ids: data.rules.node_ids || [],
      country_filter: data.rules.country_filter || [],
      type_filter: data.rules.type_filter || [],
      include_keywords: data.rules.include_keywords || [],
      exclude_keywords: data.rules.exclude_keywords || []
    }
  })

  const renameRules = data.rules.rename_rules || []
  const firstRename = renameRules[0] || {}
  renameForm.prefix = firstRename.prefix || ''
  renameForm.suffix = firstRename.suffix || ''
  renameForm.replacements =
    Array.isArray(firstRename.replacements) && firstRename.replacements.length
      ? firstRename.replacements.map((item) => ({
          from: String(item.from || ''),
          to: String(item.to || '')
        }))
      : [{ from: '', to: '' }]
  renameForm.country_abbr = !!firstRename.country_abbr
  renameForm.numbered = !!firstRename.numbered
  extraRenameRules.value = renameRules.slice(1)

  const sortRules = data.rules.sort_rules || []
  const firstSort = sortRules[0] || {}
  sortForm.field = firstSort.field || 'country'
  sortForm.order = Array.isArray(firstSort.order) ? [...firstSort.order] : []
  sortForm.direction =
    firstSort.direction === 'asc' || firstSort.direction === 'desc'
      ? firstSort.direction
      : 'custom'
  extraSortRules.value = sortRules.slice(1)
  priorityInput.value = ''
  dialogVisible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写套餐名称')
    return
  }
  const renameRule = {}
  if (renameForm.prefix) renameRule.prefix = renameForm.prefix
  if (renameForm.suffix) renameRule.suffix = renameForm.suffix
  const replacements = renameForm.replacements
    .filter((item) => item.from && item.from.trim())
    .map((item) => ({ from: item.from.trim(), to: (item.to || '').trim() }))
  if (replacements.length) renameRule.replacements = replacements
  if (renameForm.country_abbr) renameRule.country_abbr = true
  if (renameForm.numbered) renameRule.numbered = true
  const rename_rules = Object.keys(renameRule).length
    ? [renameRule, ...extraRenameRules.value]
    : [...extraRenameRules.value]

  const sortRule = { field: sortForm.field || 'country' }
  if (sortForm.order.length) sortRule.order = [...sortForm.order]
  if (sortForm.direction === 'asc' || sortForm.direction === 'desc') {
    sortRule.direction = sortForm.direction
  }
  const sort_rules = [sortRule, ...extraSortRules.value]

  saving.value = true
  try {
    const payload = {
      ...form,
      expires_at: toUtcIso(form.expires_at),
      rules: {
        ...form.rules,
        rename_rules,
        sort_rules
      }
    }
    if (editing.value) {
      await updatePackage(editing.value.id, payload)
    } else {
      const { data } = await createPackage(payload)
      ElMessageBox.alert(
        `订阅 Token：${data.token}\n订阅地址：${data.subscription_url}`,
        '套餐已创建（Token 仅显示一次）',
        { confirmButtonText: '我已保存' }
      )
    }
    dialogVisible.value = false
    ElMessage.success(editing.value ? '套餐已更新' : '套餐创建成功')
    await load()
  } finally {
    saving.value = false
  }
}

async function copyUrl(row) {
  if ((packageNodeCounts.value[row.id] ?? 0) <= 0) {
    ElMessage.warning('当前套餐暂无可用节点')
    return
  }
  try {
    const { data } = await getPackageSubscriptionUrl(row.id)
    await navigator.clipboard.writeText(data.subscription_url)
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function showQr(row) {
  if ((packageNodeCounts.value[row.id] ?? 0) <= 0) {
    ElMessage.warning('当前套餐暂无可用节点')
    return
  }
  try {
    const { data } = await getPackageSubscriptionUrl(row.id)
    qrUrl.value = data.subscription_url
    qrName.value = row.subscription_name || row.name
    qrDataUrl.value = await QRCode.toDataURL(data.subscription_url, {
      width: 240,
      margin: 1
    })
    qrVisible.value = true
  } catch {
    ElMessage.error('订阅地址或二维码生成失败')
  }
}

async function copyQrUrl() {
  try {
    await navigator.clipboard.writeText(qrUrl.value)
    ElMessage.success('订阅地址已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function regenerate(row) {
  const { data } = await regenerateToken(row.id)
  ElMessageBox.alert(
    `新 Token：${data.token}\n订阅地址：${data.subscription_url}`,
    'Token 已重生成（旧 Token 立即失效）',
    { confirmButtonText: '我已保存' }
  )
  await load()
}

async function duplicate(row) {
  const defaultName = `${row.name}-副本`
  let value
  try {
    const result = await ElMessageBox.prompt(
      '复制会创建全新的套餐和 Token，副本默认停用且不会继承原套餐归属。',
      '复制套餐',
      {
        confirmButtonText: '创建副本',
        cancelButtonText: '取消',
        inputValue: defaultName,
        inputPattern: /\S+/,
        inputErrorMessage: '请输入套餐名称'
      }
    )
    value = result.value
  } catch {
    return
  }
  const { data } = await duplicatePackage(row.id, { name: value.trim() })
  await ElMessageBox.alert(
    `新 Token：${data.token}\n订阅地址：${data.subscription_url}\n\n副本当前已停用，请编辑确认后再启用。`,
    '套餐副本已创建（Token 仅显示一次）',
    { confirmButtonText: '我已保存' }
  )
  await load()
}

async function toggle(row) {
  await togglePackage(row.id)
  ElMessage.success(row.enabled ? '已禁用套餐' : '已启用套餐')
  await load()
}

async function preview(row) {
  const { data } = await previewPackage(row.id)
  previewRows.value = data
  previewVisible.value = true
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `删除「${row.name}」后，该订阅地址将立即失效。`,
      '删除套餐？',
      {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '取消'
      }
    )
  } catch {
    return
  }
  await deletePackage(row.id)
  ElMessage.success('已删除')
  await load()
}

async function handleMore(command, row) {
  if (command === 'preview') await preview(row)
  if (command === 'duplicate') await duplicate(row)
  if (command === 'regenerate') await regenerate(row)
  if (command === 'toggle') await toggle(row)
  if (command === 'delete') await remove(row)
}

function formatTime(value) {
  return formatApiDate(value)
}

async function findPackageBySubscription() {
  const query = packageLookupQuery.value.trim()
  if (!query) {
    ElMessage.warning('请输入订阅链接、Token 或 Token 前缀')
    return
  }
  packageLookupLoading.value = true
  packageLookupSearched.value = true
  try {
    const { data } = await lookupPackages(query)
    packageLookupResults.value = data
    if (!data.length) ElMessage.warning('未找到匹配套餐')
  } catch (error) {
    packageLookupResults.value = []
    if (error.response?.status === 422) ElMessage.warning('请输入有效的订阅链接或 Token')
    else ElMessage.error('查找套餐失败')
  } finally {
    packageLookupLoading.value = false
  }
}

function clearPackageLookup() {
  packageLookupQuery.value = ''
  packageLookupResults.value = []
  packageLookupSearched.value = false
}

async function openLookupPackage(row) {
  await openEdit({ id: row.package_id })
}

function packageLookupKindLabel(value) {
  return ({
    package: '套餐 Token',
    package_prefix: '套餐 Token 前缀',
    customer_subscription: '客户订阅 Token',
    customer_subscription_prefix: '客户订阅前缀',
    customer_subscription_history: '历史 Token'
  })[value] || '订阅匹配'
}

let expiryTimer

onMounted(() => {
  load()
  loadSources()
  loadUsers()
  loadSelfNodes()
  expiryTimer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 60 * 1000)
})

onUnmounted(() => {
  if (expiryTimer) window.clearInterval(expiryTimer)
})
</script>

<style scoped>
.spacer {
  flex: 1;
}

.filter-hint {
  color: var(--app-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.package-view-switch {
  flex-shrink: 0;
}

.package-view-switch :deep(.el-radio-button__inner) {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
}

.dialog-subtitle {
  margin: 0 0 16px;
  color: var(--app-text-secondary);
  font-size: 13px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.expiry-quick-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
}

.expiry-quick-actions .form-hint {
  margin-top: 0;
}

.package-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  min-height: 200px;
}

.package-card {
  flex: 1 1 520px;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.package-card:hover {
  border-color: var(--app-border-strong);
  box-shadow: 0 4px 12px rgba(16, 24, 40, 0.06);
}

.package-table-wrap {
  min-height: 200px;
  padding: 0;
  overflow: hidden;
}

.package-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  min-height: 58px;
  margin-top: 14px;
  padding: 10px 14px;
  border-top: 1px solid var(--app-border);
}

.package-pagination-hint {
  margin-right: auto;
  color: var(--app-text-muted);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.package-table-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.package-table-main strong {
  overflow: hidden;
  color: var(--app-text);
  font-size: 13px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.package-table-main span {
  overflow: hidden;
  color: var(--app-text-muted);
  font-size: 12px;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.package-table-dates span {
  font-variant-numeric: tabular-nums;
}

.package-table-status {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.package-table-status > span {
  max-width: 118px;
  overflow: hidden;
  color: var(--app-text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.package-table-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.table-index {
  color: var(--app-text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.table-muted,
.table-danger {
  color: var(--app-text-muted) !important;
  font-weight: 500 !important;
}

.table-danger {
  color: var(--el-color-danger) !important;
}

.package-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 19px;
  font-weight: 700;
  color: var(--app-text);
}

.package-index {
  color: var(--app-text-secondary);
  font-variant-numeric: tabular-nums;
}

.package-sub {
  margin-top: 4px;
  font-size: 13px;
  color: var(--app-text-muted);
}

.package-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.meta-block {
  background: #fafbfc;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 10px 12px;
}

.meta-label {
  font-size: 13px;
  color: var(--app-text-muted);
  margin-bottom: 4px;
}

.meta-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--app-text);
  word-break: break-all;
}

.source-warning {
  margin-top: 6px;
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.no-nodes {
  color: var(--app-text-muted);
  font-weight: 500;
}

.package-updated {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid var(--app-border);
}

.package-usage { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--app-border); }
.usage-names { color: var(--app-text-secondary); font-size: 12px; }
.usage-empty { color: var(--app-text-muted); font-size: 12px; }
.owner-picker { display: flex; align-items: center; gap: 8px; width: 100%; }
.owner-picker .el-select { flex: 1; }

.package-date-end {
  text-align: right;
}

.updated-value {
  font-size: 13px;
  color: var(--app-text-secondary);
}

.package-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  flex-wrap: wrap;
}

.package-actions .el-button {
  height: 36px;
  font-size: 14px;
}

.package-empty {
  width: 100%;
}

.node-source-box {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  width: 100%;
}

.source-group {
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: 12px;
}

.source-group-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}

.source-check-list {
  max-height: 220px;
  overflow-y: auto;
  margin-bottom: 8px;
}

.source-group > .source-warning {
  margin-bottom: 8px;
}

.source-check,
.self-node-check {
  display: flex;
  width: 100%;
  height: auto;
  margin-right: 0;
  padding: 6px 0;
  white-space: normal;
}

.self-node-list {
  max-height: 220px;
  overflow-y: auto;
  margin-top: 8px;
  margin-bottom: 8px;
}

.self-node-check {
  flex-direction: column;
  align-items: flex-start;
}

.node-option-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--app-text);
}

.node-option-meta {
  margin-top: 2px;
  font-size: 13px;
  color: var(--app-text-secondary);
}

.source-actions {
  display: flex;
  gap: 8px;
}

.qr-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.qr-image {
  width: 240px;
  height: 240px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
}

.qr-url {
  max-width: 100%;
  font-size: 13px;
  color: var(--app-text-secondary);
  word-break: break-all;
  text-align: center;
}

.keyword-box {
  width: 100%;
}

.keyword-add {
  display: flex;
  gap: 8px;
}

.keyword-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.rename-list {
  width: 100%;
}

.rename-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.arrow {
  color: var(--app-text-muted);
}

.rule-options {
  display: flex;
  gap: 16px;
  margin-top: 8px;
}

.rule-extra {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.priority-add {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.priority-list {
  width: 100%;
}

.priority-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  margin-bottom: 6px;
}

.priority-index {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: #f2f4f7;
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.priority-value {
  flex: 1;
  font-size: 13px;
  color: var(--app-text);
}

.package-lookup-panel,
.package-lookup-results {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 16px;
  padding: 14px 16px;
}

.package-lookup-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 250px;
}

.package-lookup-copy strong,
.package-lookup-results-head strong,
.package-lookup-main strong {
  color: var(--app-text);
}

.package-lookup-copy span,
.package-lookup-results-head span,
.lookup-secondary,
.package-lookup-main span {
  color: var(--app-text-muted);
  font-size: 12px;
}

.package-lookup-input {
  flex: 1;
}

.package-lookup-results {
  display: block;
}

.package-lookup-results-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.package-lookup-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

@media (max-width: 768px) {
  .filter-hint {
    width: 100%;
  }

  .package-lookup-panel {
    align-items: stretch;
    flex-direction: column;
  }

  .package-lookup-copy {
    min-width: 0;
  }

  .package-view-switch {
    width: 100%;
  }

  .package-view-switch .el-radio-button {
    flex: 1;
  }

  .package-view-switch :deep(.el-radio-button__inner) {
    justify-content: center;
    width: 100%;
  }

  .package-pagination {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .package-pagination-hint {
    margin-right: 0;
  }

  .package-pagination :deep(.el-pagination) {
    flex-wrap: wrap;
    justify-content: flex-start;
  }

  .package-meta {
    grid-template-columns: 1fr;
  }

  .node-source-box {
    grid-template-columns: 1fr;
  }

  .form-row {
    flex-direction: column;
    gap: 0;
  }
}
</style>
