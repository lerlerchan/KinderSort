'use strict';

const translations = {
  en: {
    announcement: 'Made for teachers. Designed to work offline.',
    nav_features: 'Features', nav_guide: 'How it works', nav_faq: 'FAQ', nav_download: 'Get KinderSort',
    eyebrow: 'THE SIMPLER WAY TO SORT SCHOOL PHOTOS', hero_title: 'More memories.<br /><em>Less sorting.</em>',
    hero_lead: 'From sports days to school trips, KinderSort helps teachers organise event photos by student — right on their own computer.',
    hero_button: 'Download for Windows', hero_how: 'See how it works', proof_1: 'Offline by design', proof_2: 'Original photos stay untouched',
    mock_title: 'Your photos, organised.', mock_subtitle: 'Student Photo Organiser', mock_reference: 'Reference photos', mock_event: 'Event photos', mock_output: 'Output folder', mock_progress: 'Sorting photos', mock_complete: 'Ready to review', folder_photos: 'Photos sorted', illustration_note: 'Illustration · not a screenshot of the app',
    trust_windows: 'Made for Windows', trust_offline: 'No cloud upload', trust_copy: 'Copies, not moves', trust_teachers: 'Built for educators',
    features_kicker: 'A LITTLE LESS ADMIN, A LOT MORE TIME', features_title: "The good part of the day<br /><em>isn't sorting files.</em>", features_lead: 'KinderSort handles the repetitive organisation work so you can get back to sharing those memorable classroom moments.',
    feature_one_title: 'Face-based matching', feature_one_text: 'Matches faces in event photos against the reference photos you provide.',
    feature_two_title: 'Folders, automatically', feature_two_text: 'Creates student folders and copies matching photos to the right places.',
    feature_three_title: 'Group photo friendly', feature_three_text: "One group photo can be copied into multiple students' folders.",
    feature_four_title: 'See what happened', feature_four_text: 'A summary and local log help you review matches, unmatched photos and processing errors.',
    workflow_kicker: 'FOUR SIMPLE STEPS', workflow_title: 'From messy camera roll<br />to <em>neatly sorted folders.</em>', workflow_lead: 'No complicated setup. Just point KinderSort to the folders on your Windows computer.',
    step_one_title: 'Add reference photos', step_one_text: "Prepare one clear front-facing photo per student, with the student's name as the filename.",
    step_two_title: 'Choose event photos', step_two_text: 'Select a folder with photos from sports days, trips or other school activities.',
    step_three_title: 'Start sorting', step_three_text: 'Let KinderSort process photos locally. Time needed depends on your computer and images.',
    step_four_title: 'Review the results', step_four_text: 'Check each student folder and manually verify important matches before sharing photos.',
    guide_title: 'Need a hand setting things up?', guide_text: 'Our step-by-step teacher guide walks you through folders, common issues and what to expect.', guide_link: 'Read the teacher guide',
    privacy_kicker: 'YOUR PHOTOS, YOUR COMPUTER', privacy_title: 'Memories belong<br /><em>with your school.</em>', privacy_text: 'KinderSort is a desktop application. Photo processing happens locally — the website does not upload or process student images.', privacy_small: 'Teachers should still follow school privacy rules, protect local folders and review matching results before sharing.',
    download_kicker: 'READY WHEN YOU ARE', download_title: 'Give your photo folders<br />a little <em>breathing room.</em>', download_lead: 'Get the latest publicly released Windows version from the official KinderSort GitHub repository.', download_button: 'Download v1.2 (.exe)', download_release: 'View release details', release_note: 'Windows · Public release v1.2 · No installation required. This release predates the fixes proposed in PR #15; those changes are not included in this download.',
    faq_kicker: 'GOOD TO KNOW', faq_title: 'A few quick<br /><em>questions.</em>', faq_lead: 'Answers to the things teachers usually want to know before getting started.',
    faq_one_q: 'Do I need an internet connection?', faq_one_a: 'No. Photo sorting runs on your Windows computer without uploading images to a cloud service. You only need internet to visit this website or download the application.',
    faq_two_q: 'What happens to my original photos?', faq_two_a: 'KinderSort copies photos into output folders; it does not move or delete the original input photos. Start with a separate output folder and keep backups of important school files.',
    faq_three_q: 'Can it organise group photos?', faq_three_a: "Yes. A group photo may be copied to more than one student's folder if multiple students are matched. Always review results for accuracy.",
    faq_four_q: "What if a face isn't recognised?", faq_four_a: 'Photos without a student match go to _unmatched. Processing errors may also preserve readable copies there; check the summary and log to tell the difference.',
    footer_tagline: 'Less time organising. More time remembering.', footer_releases: 'Releases', footer_guide: "Teacher's guide", footer_note: 'An unofficial preview of the project website. Not yet published or endorsed by the repository owner.', footer_back: 'Back to top ↑'
  },
  zh: {
    announcement: '为老师而设计，无需联网即可整理照片。',
    nav_features: '主要功能', nav_guide: '使用方法', nav_faq: '常见问题', nav_download: '获取 KinderSort',
    eyebrow: '让学校活动照片整理变得更简单', hero_title: '珍藏更多回忆。<br /><em>减少整理时间。</em>',
    hero_lead: '从运动会到校外活动，KinderSort 帮助老师按照学生姓名分类活动照片，所有处理都在自己的电脑上完成。',
    hero_button: '下载 Windows 版本', hero_how: '了解使用方法', proof_1: '离线运行', proof_2: '不修改原始照片',
    mock_title: '照片整理完成。', mock_subtitle: '学生照片分类工具', mock_reference: '学生参考照片', mock_event: '活动照片', mock_output: '输出文件夹', mock_progress: '正在分类照片', mock_complete: '可以检查结果', folder_photos: '照片已分类', illustration_note: '示意图 · 非软件真实截图',
    trust_windows: '支持 Windows', trust_offline: '无需上传云端', trust_copy: '复制而非移动', trust_teachers: '专为教育工作者设计',
    features_kicker: '少一些重复工作，多一点宝贵时间', features_title: '老师的宝贵时间<br /><em>不该耗在整理文件上。</em>', features_lead: '让 KinderSort 处理重复的照片分类工作，把更多时间留给教学与分享美好的校园时刻。',
    feature_one_title: '人脸匹配', feature_one_text: '将活动照片中的人脸与老师提供的学生参考照片进行比对。',
    feature_two_title: '自动整理文件夹', feature_two_text: '按学生姓名创建文件夹，并将匹配的照片复制到对应位置。',
    feature_three_title: '支持合照', feature_three_text: '一张合照可以同时复制到多名学生的文件夹。',
    feature_four_title: '结果清晰可查', feature_four_text: '通过分类摘要和本地日志检查匹配、未匹配照片及处理错误。',
    workflow_kicker: '简单四步即可使用', workflow_title: '从杂乱活动照片<br />变成<em>整齐的学生文件夹。</em>', workflow_lead: '无需复杂设置，只需在 Windows 电脑中选择三个文件夹。',
    step_one_title: '准备参考照片', step_one_text: '每位学生提供一张清楚的正面照片，并以学生姓名命名文件。',
    step_two_title: '选择活动照片', step_two_text: '选择包含运动会、旅行或其他校园活动照片的文件夹。',
    step_three_title: '开始分类', step_three_text: 'KinderSort 会在本机处理照片，所需时间取决于电脑性能和照片内容。',
    step_four_title: '检查分类结果', step_four_text: '查看每位学生的输出文件夹，分享前请人工核对重要照片。',
    guide_title: '不知道怎样开始？', guide_text: '老师使用指南包含详细操作步骤、文件夹说明及常见问题处理方法。', guide_link: '阅读老师使用指南',
    privacy_kicker: '照片留在自己的电脑', privacy_title: '校园的珍贵回忆<br /><em>由学校自己保管。</em>', privacy_text: 'KinderSort 是桌面应用程序，照片在电脑本地处理。这个网站不会上传或处理学生照片。', privacy_small: '使用者仍应遵守学校的隐私规定，保护本地文件夹，并在分享前人工核对匹配结果。',
    download_kicker: '准备开始了吗？', download_title: '让照片文件夹<br /><em>变得井井有条。</em>', download_lead: '从 KinderSort 官方 GitHub 仓库获取目前公开发布的 Windows 版本。', download_button: '下载 v1.2（.exe）', download_release: '查看版本说明', release_note: 'Windows · 公开版本 v1.2 · 无需安装。此版本早于 PR #15 的安全修复，下载程序尚未包含这些待审查的修改。',
    faq_kicker: '使用前须知', faq_title: '几个常见<br /><em>问题。</em>', faq_lead: '整理了老师在使用前通常会提出的问题。',
    faq_one_q: '需要网络连接吗？', faq_one_a: '不需要。照片分类在 Windows 电脑本地进行，不会上传到云端。只有访问网站或下载程序时才需要网络。',
    faq_two_q: '原始照片会发生什么变化？', faq_two_a: 'KinderSort 会把照片复制到输出文件夹，不会移动或删除输入的原始照片。建议使用独立的输出目录，并为重要文件保留备份。',
    faq_three_q: '可以整理多人合照吗？', faq_three_a: '可以。若合照匹配到多名学生，照片可能被复制到多位学生的文件夹。但请始终检查分类准确性。',
    faq_four_q: '有些人脸识别不到怎么办？', faq_four_a: '未匹配到学生的照片会进入 _unmatched 文件夹。部分处理错误也可能在这里保留可读取的原始副本，请结合分类摘要和日志判断。',
    footer_tagline: '少一些整理时间，多一些美好回忆。', footer_releases: '版本下载', footer_guide: '老师使用指南', footer_note: '此网站为非正式预览版本，尚未正式发布，也未获得仓库所有者确认。', footer_back: '返回顶部 ↑'
  }
};

const switchButton = document.getElementById('language-switch');
const switchLabel = document.getElementById('language-label');
const preferred = (() => {
  try { return window.localStorage.getItem('kindersort-language'); } catch { return null; }
})();
let currentLanguage = preferred === 'zh' || preferred === 'en' ? preferred : (navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en');

function setLanguage(language) {
  const words = translations[language];
  if (!words) return;
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach(element => {
    const translated = words[element.dataset.i18n];
    if (typeof translated === 'string') element.textContent = translated;
  });
  document.querySelectorAll('[data-i18n-html]').forEach(element => {
    const translated = words[element.dataset.i18nHtml];
    // Only trusted, static translation strings from this source file are used.
    if (typeof translated === 'string') element.innerHTML = translated;
  });
  switchLabel.textContent = language === 'en' ? '中文' : 'EN';
  switchButton.setAttribute('aria-label', language === 'en' ? 'Switch to Chinese' : 'Switch to English');
  document.title = language === 'en' ? 'KinderSort — Every memory, neatly organised.' : 'KinderSort — 让校园照片整理更简单';
  currentLanguage = language;
  try { window.localStorage.setItem('kindersort-language', language); } catch { /* Optional preference. */ }
}

switchButton.addEventListener('click', () => setLanguage(currentLanguage === 'en' ? 'zh' : 'en'));
setLanguage(currentLanguage);
