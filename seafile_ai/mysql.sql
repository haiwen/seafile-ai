CREATE TABLE IF NOT EXISTS `index_repo`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `repo_id` varchar(36) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated` datetime(6),
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE KEY `repo_id`(`repo_id`)
) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8;
