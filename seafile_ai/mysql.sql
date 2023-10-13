CREATE TABLE IF NOT EXISTS `library_sdoc_index`  (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `associate_id` varchar(36) NOT NULL,
  `last_modify` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated` datetime(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `repo_id`(`associate_id`)
) ENGINE = InnoDB DEFAULT CHARACTER SET = utf8;
