package com.healthcare.referral.repository;

import com.healthcare.referral.domain.entity.CommunicationLog;
import com.healthcare.referral.domain.enums.CommunicationChannel;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface CommunicationLogRepository extends JpaRepository<CommunicationLog, Long> {

    List<CommunicationLog> findByReferralIdOrderByCreatedAtDesc(Long referralId);

    List<CommunicationLog> findByReferralIdAndChannel(Long referralId, CommunicationChannel channel);
}