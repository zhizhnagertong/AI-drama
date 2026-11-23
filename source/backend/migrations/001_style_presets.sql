-- 001_style_presets.sql
-- 风格预设表（与 app/models.py StylePreset 一致）
-- 注：应用启动时 Base.metadata.create_all 会自动建表，本脚本供手工迁移 / 审查使用。

CREATE TABLE IF NOT EXISTS style_presets (
    id INT NOT NULL AUTO_INCREMENT,
    user_id INT NOT NULL,
    name VARCHAR(64) NOT NULL,
    prompt TEXT NOT NULL,
    description VARCHAR(256) NULL,
    negative_prompt TEXT NULL,
    color VARCHAR(32) NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_style_presets_user_id (user_id),
    CONSTRAINT uq_style_presets_user_name UNIQUE (user_id, name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- 默认风格示例（user_id 为占位：实际由后端 ensure_default_styles 在注册/首次拉取时按用户写入）
-- 将 @uid 替换为目标用户 id 后执行：
-- SET @uid = 1;
-- INSERT INTO style_presets (user_id, name, prompt, description, color, is_active, sort_order, created_at, updated_at) VALUES
-- (@uid, '赛博朋克', 'cyberpunk, neon lights, futuristic city, high contrast, cyan and magenta color grading', '霓虹光效、未来都市', '#00E5FF', 1, 1, NOW(), NOW()),
-- (@uid, '水墨国风', 'Chinese ink wash painting, traditional shuimo style, soft brush strokes, misty mountains, elegant oriental aesthetic', '水墨笔触、东方意境', '#546E7A', 1, 2, NOW(), NOW()),
-- (@uid, '日系动漫', 'Japanese anime style, clean line art, vibrant saturated colors, cel shading, expressive eyes', '清新线条、高饱和', '#FF6B9D', 1, 3, NOW(), NOW()),
-- (@uid, '美式漫画', 'American comic book style, bold outlines, high contrast shading, halftone dots, dynamic heroic composition', '强对比块面、硬派', '#F4511E', 1, 4, NOW(), NOW()),
-- (@uid, '3D卡通', '3D cartoon render, Pixar style, rounded soft shapes, toy-like texture, bright cheerful lighting', '圆润立体、玩具质感', '#FFB300', 1, 5, NOW(), NOW()),
-- (@uid, '写实', 'photorealistic, cinematic lighting, fine details, shallow depth of field, film grain, 8k quality', '电影感光影、细节', '#8D6E63', 1, 6, NOW(), NOW());
